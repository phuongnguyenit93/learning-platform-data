# Kiểm tra lỗi IO, quyền truy cập, đóng stream và dọn tài nguyên

Một chức năng upload tài liệu trong Spring Boot có thể chạy tốt với file nhỏ và directory có quyền ghi, nhưng gặp sự cố khi volume đầy, file bị khóa, người dùng hệ điều hành không có quyền truy cập, stream đọc bị cắt giữa chừng, hoặc thao tác đổi tên file tạm thất bại. Nếu test chỉ xác nhận `HTTP 201` ở happy path, ứng dụng có thể để lại file `.tmp` chứa dữ liệu dở dang, rò file descriptor, trả đường dẫn nội bộ cho client, hoặc báo thành công trước khi dữ liệu thực sự được lưu.

Bài Knowledge này thuộc **Tích hợp bổ sung** trong module **Spring Boot – testing**, tập trung vào bốn nhóm lỗi đi cùng nhau: **lỗi IO**, **quyền truy cập**, **vòng đời stream** và **dọn tài nguyên**. Ta sẽ thiết kế một file store có ranh giới IO rõ, mô phỏng `AccessDeniedException`, lỗi đọc/ghi/đóng stream, kiểm cleanup khi `move` lỗi, rồi kiểm API multipart bằng `MockMvc`. Trọng tâm không phải viết một dịch vụ lưu trữ production hoàn chỉnh, mà là hình thành thói quen **test cả nhánh thất bại và hậu điều kiện trên tài nguyên**.

Ví dụ dùng **Java 17+, Spring Boot 3.5.16, JUnit Jupiter 5, Mockito, Spring MVC, MockMvc, @TempDir và NIO.2 (java.nio.file)**. Dữ liệu là file giả chỉ nằm trong thư mục test. Các lỗi quyền được mô phỏng **có kiểm soát** thay vì phụ thuộc `chmod` hay người chạy CI có phải root/administrator hay không. Mẫu bảo đảm stream được đóng và file staging được xóa trong các lỗi được mô phỏng; nó không tự thay thế mọi kiểm thử về disk crash, durability, antivirus/file lock, symlink race hoặc filesystem đặc thù.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Nhận diện `IOException`, `NoSuchFileException`, `AccessDeniedException`, `FileAlreadyExistsException`, `FileSystemException`, `EOFException`, `UncheckedIOException` và ngữ cảnh sử dụng.
- Phân biệt lỗi **xác thực/phân quyền HTTP 401/403** với lỗi **filesystem ACL/quyền của process**; không tự map mọi AccessDeniedException thành HTTP 403.
- Quy định rõ **ai sở hữu InputStream/OutputStream** và ai phải gọi `close()`.
- Dùng `try-with-resources` để đóng stream khi thành công, lỗi đọc, lỗi ghi hoặc lỗi `close`.
- Hiểu thứ tự đóng resources và cơ chế `Throwable.getSuppressed()`.
- Giải thích tại sao `Files.copy(InputStream, Path)` không có nghĩa nó tự đóng InputStream.
- Ghi qua file staging rồi mới publish tới đích để tránh file hoàn chỉnh bị nhìn thấy khi copy dở.
- Dọn file tạm khi copy/move thất bại, không xóa file đã publish thành công.
- Kiểm hậu điều kiện: không có `.part` còn lại, không có file chính thức sai, input stream đã đóng.
- Dùng `@TempDir` để cô lập file thật, Mockito spy/fake IO adapter để mô phỏng exception quyết định được.
- Không dựa vào permission bits POSIX khi test chạy trên Windows/CI có quyền cao.
- Kiểm `MockMvc.multipart(...)`, JSON error contract và không lộ đường dẫn nội bộ.
- Phân biệt test MVC mock multipart với test parser/socket thật ở `RANDOM_PORT`.
- Bảo vệ path traversal, symlink abuse, giới hạn kích thước, duplicate IDs và quyền trên thư mục lưu trữ.
- Thiết kế cleanup cho DB/Redis/object storage/transaction/file handles theo cùng nguyên lý ownership.

## 2. Bốn tầng lỗi cần phân biệt

```text
HTTP caller
   |
   | multipart/form-data
   v
Spring MVC / MultipartResolver
   |  - request quá lớn / malformed multipart
   |  - servlet temp files
   v
DocumentController
   |  - người dùng có quyền upload không?
   |  - validation và lỗi công khai
   v
LocalDocumentStore
   |  - nhận quyền sở hữu InputStream
   |  - tạo .part trong app-controlled directory
   |  - stream bytes vào staging file
   |  - đóng OutputStream và InputStream
   |  - move staging -> generated final name
   v
NIO / filesystem / OS
   |  - read failure, write failure, disk full
   |  - AccessDeniedException, lock, quota
   |  - rename/move failure, cleanup failure
   v
HTTP response:
  201 khi đã lưu
  400 ID không hợp lệ
  404 file không tồn tại
  413 file vượt giới hạn của store
  500 lỗi IO/server storage (không lộ absolute path)
```

**Không một layer có thể thay thế tất cả layer còn lại.** `@WebMvcTest` với mocked store chứng minh controller map errors đúng; unit test store với NIO thật chứng minh cleanup/read/write logic; test permission bằng fake IO làm failure injection deterministic; real HTTP integration mới kiểm multipart parser/container/proxy.

### 2.1. Bảng lỗi và nguồn lỗi

| Dấu hiệu | Nguồn khả dĩ | Điều cần xác minh |
|---|---|---|
| `NoSuchFileException` | File đã bị xóa, id không tồn tại, race | 404 nếu client tra file; không leak path |
| `AccessDeniedException` | Process thiếu quyền trên file/directory | Không publish thành công; stream đóng; lỗi public an toàn |
| `FileAlreadyExistsException` | Đụng tên đích hoặc đường dẫn đã có | Không overwrite dữ liệu khác |
| `FileSystemException` | Filesystem-specific (disk full, file lock...) | Phân loại/retry policy; cleanup có thể thất bại |
| `EOFException` | Đọc thiếu bytes so contract | Không coi file hoàn chỉnh |
| `IOException` khi `read` | Source/remote stream bị lỗi | Không để lại file staging |
| `IOException` khi `write/close` | Output partial, flush/close failed | Không publish partial output |
| `IOException` khi `move` | Promote không thành công/không chắc chắn | Không trả 201, dọn staging theo policy |
| `IOException` khi `delete` | Cleanup failed | Bảo toàn lỗi chính qua suppressed exceptions |
| `UncheckedIOException` | Adapter/lambda chuyển checked error | Không làm mất nguyên nhân và lifecycle |
| Socket timeout | HTTP client/remote object store | Timeout/retry/idempotency riêng |
| HTTP 403 | Security filter/ACL nghiệp vụ **hoặc** policy public | Không mặc định tương đương OS AccessDeniedException |

## 3. Checked `IOException` và taxonomy NIO.2

`IOException` là checked exception của Java, nhiều lớp con cung cấp ngữ nghĩa cụ thể:

```java
import java.io.IOException;
import java.io.EOFException;
import java.nio.file.AccessDeniedException;
import java.nio.file.NoSuchFileException;
import java.nio.file.FileAlreadyExistsException;
import java.nio.file.FileSystemException;
```

`AccessDeniedException` extends `FileSystemException`, `NoSuchFileException` và `FileAlreadyExistsException` cũng là dạng `FileSystemException`; đây là tín hiệu về filesystem và lý do OS/provider đưa ra, không tự chứa một HTTP status. Với `FileSystemException`, `getFile()`/`getOtherFile()`/`getReason()` có thể chứa đường dẫn nội bộ; **không serialize nguyên exception ra response**.

Một test nên kiểm **kiểu exception** khi type là một phần contract và kiểm **hậu điều kiện**. Chỉ assert `assertThrows(IOException.class, ...)` không đủ nếu sau lỗi vẫn còn partial file hoặc stream bị leak.

### 3.1. Đừng map tất cả IOException thành “client sai”

Lỗi đọc payload do client ngắt kết nối có thể thuộc trách nhiệm kết nối. Nhưng lỗi ghi do volume read-only, disk full hoặc quyền service account là lỗi hạ tầng máy chủ. Nếu trả HTTP 403 cho lỗi `AccessDeniedException` của tiến trình ghi file, client có thể hiểu sai rằng **người dùng cần nâng quyền ứng dụng**, trong khi thực tế volume đã hỏng hoặc service thiếu quyền.

Bài mẫu map filesystem IO generic thành **HTTP 500 + error code trung tính**. Đây là một policy minh họa; production có thể chọn 503/507 phù hợp contract, nhưng tránh lộ absolute path, stack trace hoặc permission layout. **HTTP 403 chỉ nên thể hiện phân quyền ứng dụng bị từ chối theo policy**, không là bản dịch tự động của mọi lỗi OS.

## 4. Tài nguyên nào cần đóng, và ai sở hữu chúng?

| Tài nguyên | Ai mở? | Ai đóng? | Khi lỗi giữa chừng |
|---|---|---|---|
| Upload `InputStream` từ `MultipartFile.getInputStream()` | Controller lấy stream | **FileStore** theo contract của demo | Đóng cả khi chưa tạo được temp |
| Staging `OutputStream` | FileStore gọi IO adapter | FileStore | Try-with-resources đóng trước publish |
| Download `InputStream` | FileStore đọc file | FileStore (vì trả `byte[]`) | Đóng ngay cả khi read fail |
| `Files.list(...)` `Stream<Path>` | Test/util tạo | Test/util | Try-with-resources đóng directory stream |
| `Files.walk(...)` `Stream<Path>` | Code cleanup tạo | Code cleanup | Đóng stream, tránh mở file handles |
| `ZipFile`, `ZipInputStream` | Code xử lý archive | Bên nhận ownership | Close kể cả invalid archive |
| `BufferedReader`/`BufferedWriter` | Code tạo wrapper | Owner wrapper/resource | Flush/close qua try-with-resources |
| JDBC `Connection`/`ResultSet` | Driver/pool | Theo transaction/pool contract | Không tự close connection pool dùng chung |
| HTTP response body stream | Client adapter | Người tiêu thụ response | Close/consume đúng HTTP client API |
| Multipart temp file của servlet | Servlet/container resolver | Framework/container | Không nhầm với staging file của app |

**Định nghĩa ownership trước khi viết code:** Method demo `store.save(InputStream input)` **nhận quyền sở hữu** và đóng InputStream dù thành công hay lỗi. Nếu một API khác chỉ “mượn” stream do caller sẽ dùng tiếp, nó không được tự đóng mà phải ghi rõ hợp đồng. Không có quy tắc universal “mọi method nhận InputStream đều phải close”.

### 4.1. `Files.copy` không tự đóng InputStream

Một phản ví dụ phổ biến:

```java
// PHẢN VÍ DỤ: caller không đóng input sau Files.copy.
Files.copy(input, target, StandardCopyOption.REPLACE_EXISTING);
```

JDK nói `Files.copy(InputStream, Path, ...)` sao chép bytes, có thể để file đích dở nếu lỗi; **nó không quản lý quyền sở hữu/đóng InputStream cho bạn**. Phải viết:

```java
try (InputStream input = source.openStream()) {
    Files.copy(input, target);
}
```

Đây là snippet có `source`/`target` giả định. Dù InputStream được đóng, file đích vẫn có thể được tạo dở khi copy lỗi; khi cần publish nguyên vẹn, dùng **staging + move** và cleanup như mẫu chính.

## 5. `try-with-resources`: đóng cả khi exception

```java
try (InputStream in = openInput();
     OutputStream out = openOutput()) {
    in.transferTo(out);
}
```

Trong mã minh họa, `openInput/openOutput` là factory methods chưa định nghĩa; phần sau có file runnable. Java đóng resources theo **thứ tự ngược** với thứ tự khai báo: `out.close()` trước, `in.close()` sau. Nếu đọc/ghi ném exception, Java vẫn thử đóng cả resources được khởi tạo thành công.

**Quan trọng:** `transferTo` có thể đọc lượng dữ liệu lớn không giới hạn; với upload không tin cậy phải có giới hạn kích thước tại HTTP parser/application storage layer, không đưa bytes tùy ý vào RAM/disk mà không có quota. FileStore demo dùng vòng copy có giới hạn.

### 5.1. Checked exception khi đóng stream

`close()` **cũng có thể ném IOException**. Ví dụ thiết bị lưu trữ hoặc buffered stream có thể báo lỗi khi flush/close. Để tránh báo thành công trước khi close output, mẫu sẽ:

1. Mở input và staging output.
2. Copy bytes.
3. **Đóng output**.
4. **Đóng input**.
5. **Chỉ sau đó** mới move staging sang final filename.
6. Nếu bất cứ bước 1–4 thất bại, xóa staging, không publish.

Thứ tự này tránh tình huống method đã move file, sau đó `InputStream.close()` ném lỗi khiến caller thấy failure dù file đã được publish. Tuy nhiên, move/copy trên local filesystem không tự bảo đảm durability khi OS mất điện; xem mục 29.

## 6. Suppressed exceptions: giữ lỗi gốc và lỗi cleanup

Java try-with-resources giữ lỗi chính từ body và đưa các lỗi khi `close` vào `Throwable.getSuppressed()`.

Ví dụ Java 17 độc lập:

```java
public class SuppressedDemo {
    static final class BrokenResource implements AutoCloseable {
        @Override
        public void close() throws Exception {
            throw new Exception("close failed");
        }
    }

    public static void main(String[] args) {
        try (BrokenResource ignored = new BrokenResource()) {
            throw new IllegalStateException("work failed");
        } catch (Exception e) {
            System.out.println(e.getMessage());
            System.out.println(e.getSuppressed()[0].getMessage());
        }
    }
}
```

Chạy:

```bash
javac SuppressedDemo.java
java SuppressedDemo
```

**Stdout chính xác:**

```text
work failed
close failed
```

Nếu dọn file tạm bằng `finally` thủ công và delete cũng ném lỗi, lỗi delete có thể **che lỗi copy**. Mẫu FileStore sẽ giữ một `primary` exception rồi gọi `primary.addSuppressed(cleanup)` để không mất nguyên nhân gốc. Test xác minh cả primary và suppressed khi mô phỏng move + cleanup đồng thời lỗi.

**Không im lặng nuốt cleanup failure.** Nếu không có primary exception, cleanup failure phải đi ra ngoài; nếu có primary, giữ nó và attach cleanup. Logs cần phân biệt lỗi gốc/cleanup nhưng tránh lộ đường dẫn bí mật.

## 7. Vì sao cần staging file?

Phản ví dụ:

```java
try (InputStream in = upload.getInputStream()) {
    Files.copy(in, finalPath);
}
```

Nếu copy fail giữa chừng, `finalPath` có thể đã xuất hiện với bytes thiếu. Một GET khác có thể đọc nó như file hoàn chỉnh hoặc job nền xử lý nhầm.

Quy trình chặt hơn:

```text
1. Validate request/ID, kiểm quota
2. createDirectories(root) nếu phù hợp
3. createTempFile(root, ".part-*") trong cùng filesystem
4. mở output cho staging
5. copy có giới hạn kích thước
6. close output, close input
7. move staging -> generated final filename
8. trả object ID / size
9. khi lỗi: deleteIfExists(staging), không công bố ID
```

Tạo staging trong **cùng directory/filesystem** với đích giúp có khả năng dùng atomic rename trên provider hỗ trợ, giảm cross-device move. Nhưng **`Files.move` mặc định không hứa atomicity hoặc fsync durability**. Bản demo dùng move thường để chạy đa nền tảng; production có thể yêu cầu `StandardCopyOption.ATOMIC_MOVE` và **fail** nếu `AtomicMoveNotSupportedException` thay vì tự fallback không an toàn.

### 7.1. Stage file không phải recovery journal

Một process bị `kill -9`/máy mất điện có thể không chạy Java `finally`. Stage file vẫn có thể tồn tại sau crash. Ứng dụng production nên có **janitor cleanup** cho stale stages thuộc namespace riêng, retention window rõ, metrics và tránh xóa stage của request còn hoạt động. `try-with-resources` chỉ xử lý **control flow trong JVM đang sống**.

## 8. “Quyền truy cập” gồm nhiều lớp

| Lớp | Ví dụ | Điều test nên xác minh |
|---|---|---|
| Application authorization | User A không được đọc file B | Spring Security 403/404, zero IO call |
| Filesystem permissions/ACL | Process không thể ghi vào volume | IO adapter ném AccessDeniedException |
| Container UID/GID | Kubernetes chạy non-root, volume owner khác | Integration trên container/volume thật |
| SELinux/AppArmor | OS security policy cấm file operation | Environment-specific integration |
| Object storage IAM | S3 role thiếu PutObject/DeleteObject | Mock boundary + IAM integration |
| Windows ACL/file sharing | File bị lock/missing access rights | Windows/real filesystem test |
| NFS/SMB remote permissions | Stale handle, share denial, network partition | Integration trên server thật |

**OS `AccessDeniedException` không xác minh authentication/authorization của Spring Security.** Bài mẫu kiểm OS error ở storage layer, còn security tests thực phải kiểm Principal và object ownership nếu API cho người dùng upload/download.

### 8.1. Vì sao `chmod 000` test không ổn định?

Trên Linux/macOS, `Files.setPosixFilePermissions(...)` có thể làm một path không thể đọc/ghi với user thường. Nhưng:

- Windows filesystem provider có thể không hỗ trợ `PosixFileAttributeView`.
- CI chạy với quyền root/administrator có thể vẫn truy cập dù mode bits bị xóa.
- ACL, mount flags, NFS semantics khác.
- Một test sửa permission của shared directory có thể phá test khác.
- File đã được mở trước khi permission đổi có thể tiếp tục truy cập.

Vì vậy **unit test nhánh AccessDeniedException bằng fake/spy IO adapter**, và chỉ có một vài OS-specific integration tests được bật bằng assumptions/labels trên runner phù hợp. Không khẳng định một test `chmod` xanh trên máy local sẽ giống hệt CI/cloud.

## 9. Test pyramid cho IO và resource cleanup

| Cấp | Công cụ | Bắt được | Chưa bắt được |
|---|---|---|---|
| Pure unit | Fake InputStream/OutputStream | Read/write/close failure, primary/suppressed | ACL/filesystem thật |
| Temp filesystem | JUnit `@TempDir` + `Files` | Staging/final files, readback, cleanup | Volume-specific permissions |
| IO adapter fault injection | Mockito spy/adapter | Exact AccessDenied, move/delete failure | OS-specific exception mapping hoàn toàn |
| MVC slice | `@WebMvcTest` + `MockMultipartFile` | HTTP status, JSON code, không lộ path | Multipart parser/socket thật |
| Full app MockMvc | `@SpringBootTest` + `@AutoConfigureMockMvc` | Wiring/controller/store thật | TCP/multipart parsing thật |
| Real HTTP | `RANDOM_PORT` + real multipart client | Container size/parse/temp cleanup | Cloud IAM/volume nếu môi trường khác |
| Container/volume integration | Testcontainers + mounted volume/IAM emulator | UID/GID/quota/lock provider-specific | Real cloud production hoàn toàn |

**Bài test mạnh không nhất thiết cần socket thật**, nhưng phải mô tả đúng boundary mà nó chứng minh. `MockMvc.multipart(...)` dựng `MockMultipartHttpServletRequest` trong bộ nhớ; nó không tự thử max request size/size limits của reverse proxy hoặc servlet container.

## 10. Thiết kế runnable project

Ta xây một service lưu file nhị phân an toàn ở mức demo:

- Client upload multipart qua `POST /api/documents`.
- Server tự sinh tên `UUID.bin`; **không lấy `MultipartFile.getOriginalFilename()` làm đường dẫn**.
- Mọi bytes được ghi vào file `.upload-*.part` trong directory app sở hữu.
- Chỉ khi copy và đóng input/output thành công, file staging mới được `move` sang tên final.
- Có quota 1 MiB được enforce **bên trong FileStore** (tách biệt multipart parser).
- Client có thể download qua `GET /api/documents/{id}`; FileStore đọc tối đa 1 MiB, đóng InputStream rồi trả `byte[]`.
- `StorageOps` interface tách các NIO operations để mô phỏng AccessDenied/read/write/move/delete failures.
- Error advice trả JSON code công khai, không serialize `IOException.getMessage()` chứa path.
- Dùng `@TempDir` và test injections để kiểm cleanup, stream closure.

**Cấu trúc:**

```text
io-resource-testing/
  settings.gradle
  build.gradle
  src/main/java/com/example/ioresource/
    IoResourceApplication.java
    StorageOps.java
    NioStorageOps.java
    StoredDocument.java
    FileTooLargeException.java
    InvalidDocumentIdException.java
    LocalDocumentStore.java
    StoreConfiguration.java
    DocumentController.java
    StorageErrorAdvice.java
  src/test/java/com/example/ioresource/
    LocalDocumentStoreTest.java
    DocumentControllerTest.java
    DocumentIntegrationTest.java
```

Đây là một ví dụ **một module** có Java 17, Spring Boot 3.5.16, JUnit Jupiter/Mockito. Không cần Docker, DB hay network service ngoài. Ứng dụng demo không có authentication, audit, malware scanning, encryption-at-rest, retention policy, durable catalog hay idempotency; không dùng nguyên trạng để lưu dữ liệu nhạy cảm production.

## 11. Gradle files

**`settings.gradle`**

```groovy
rootProject.name = 'io-resource-testing'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-web` cung cấp Spring MVC và JSON serialization; `spring-boot-starter-test` cung cấp JUnit Jupiter, Mockito, MockMvc, `@TempDir` thông qua JUnit và các assertion utilities. Không thêm thư viện permission/virtual filesystem nếu không cần: JDK NIO.2 cùng một adapter mockable đủ minh họa failure branches.

**Không chạy test bằng tài khoản production hoặc đường dẫn upload thật.** Property storage path mặc định của demo đi vào `./build/io-store` trong project khi không override, không phải đường dẫn nhạy cảm trên host.

## 12. Spring Boot bootstrap

**`src/main/java/com/example/ioresource/IoResourceApplication.java`**

```java
package com.example.ioresource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IoResourceApplication {
    public static void main(String[] args) {
        SpringApplication.run(IoResourceApplication.class, args);
    }
}
```

Application tự quét `@Component NioStorageOps`, `@Configuration StoreConfiguration`, controller và advice trong cùng package. Các unit tests storage tạo objects trực tiếp, không cần khởi động Spring context.

## 13. IO adapter: cô lập những lời gọi NIO có thể thất bại

**`src/main/java/com/example/ioresource/StorageOps.java`**

```java
package com.example.ioresource;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Path;

public interface StorageOps {

    void createDirectories(Path directory) throws IOException;

    Path createTempFile(Path directory) throws IOException;

    OutputStream openOutput(Path path) throws IOException;

    InputStream openInput(Path path) throws IOException;

    void move(Path source, Path destination) throws IOException;

    void deleteIfExists(Path path) throws IOException;
}
```

**`src/main/java/com/example/ioresource/NioStorageOps.java`**

```java
package com.example.ioresource;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import org.springframework.stereotype.Component;

@Component
public class NioStorageOps implements StorageOps {

    @Override
    public void createDirectories(Path directory)
            throws IOException {
        Files.createDirectories(directory);
    }

    @Override
    public Path createTempFile(Path directory)
            throws IOException {
        return Files.createTempFile(
                directory, ".upload-", ".part");
    }

    @Override
    public OutputStream openOutput(Path path)
            throws IOException {
        return Files.newOutputStream(
                path,
                StandardOpenOption.WRITE,
                StandardOpenOption.TRUNCATE_EXISTING);
    }

    @Override
    public InputStream openInput(Path path)
            throws IOException {
        return Files.newInputStream(
                path, StandardOpenOption.READ);
    }

    @Override
    public void move(Path source, Path destination)
            throws IOException {
        Files.move(source, destination);
    }

    @Override
    public void deleteIfExists(Path path)
            throws IOException {
        Files.deleteIfExists(path);
    }
}
```

**Tại sao dùng interface?** Thay vì test sửa ACL thật, Mockito có thể làm `createDirectories`, `createTempFile`, `openOutput`, `move` hoặc `deleteIfExists` ném exception một cách có kiểm soát. Khi không mock, `NioStorageOps` chạy trực tiếp JDK `Files`, nhờ vậy test `@TempDir` thực sự xác minh disk state.

**Quan trọng với production security:** Mẫu `Files.newInputStream`/`newOutputStream` không sử dụng `SecureDirectoryStream`, `NOFOLLOW_LINKS` hay chặn mọi symlink race. Nó giả định **directory là private và attacker không có quyền sửa entries**. Khi storage directory bị external process không đáng tin ghi được, cần cơ chế an toàn với symlinks/openat/ACL hoặc dùng object storage có identity policy thích hợp.

## 14. Value objects và exception loại dữ liệu đầu vào

**`src/main/java/com/example/ioresource/StoredDocument.java`**

```java
package com.example.ioresource;

public record StoredDocument(String id, long bytes) {
}
```

**`src/main/java/com/example/ioresource/FileTooLargeException.java`**

```java
package com.example.ioresource;

import java.io.IOException;

public class FileTooLargeException extends IOException {
    public FileTooLargeException(String message) {
        super(message);
    }
}
```

**`src/main/java/com/example/ioresource/InvalidDocumentIdException.java`**

```java
package com.example.ioresource;

public class InvalidDocumentIdException
        extends IllegalArgumentException {

    public InvalidDocumentIdException() {
        super("Invalid document identifier");
    }
}
```

Chủ ý dùng **exception type riêng** cho invalid ID thay vì handler bắt mọi `IllegalArgumentException` của application; một bug lập trình không nên bị hiển thị thành lỗi 400 của client. `FileTooLargeException` là IOException chuyên biệt giúp map thành 413 ở upload. Còn `AccessDeniedException` của NIO để map như một lỗi storage hạ tầng; không in file path vào response.

## 15. LocalDocumentStore: đóng stream trước khi publish

**`src/main/java/com/example/ioresource/LocalDocumentStore.java`**

```java
package com.example.ioresource;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Objects;
import java.util.UUID;
import java.util.regex.Pattern;

public final class LocalDocumentStore {

    private static final Pattern DOCUMENT_ID = Pattern.compile(
            "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            + "[0-9a-f]{4}-[0-9a-f]{12}\\.bin$");

    private final Path root;
    private final StorageOps ops;
    private final long maxBytes;

    public LocalDocumentStore(
            Path root, StorageOps ops, long maxBytes) {
        this.root = Objects.requireNonNull(
                root, "root").toAbsolutePath().normalize();
        this.ops = Objects.requireNonNull(ops, "ops");
        if (maxBytes <= 0) {
            throw new IllegalArgumentException(
                    "maxBytes must be positive");
        }
        this.maxBytes = maxBytes;
    }

    public StoredDocument save(InputStream input)
            throws IOException {

        Objects.requireNonNull(input, "input");

        Path staged = null;
        boolean promoted = false;
        Throwable primary = null;
        long byteCount = 0L;
        String id = UUID.randomUUID() + ".bin";

        try {
            // Store owns input. It closes even if mkdir/create fails.
            try (InputStream source = input) {
                ops.createDirectories(root);
                staged = ops.createTempFile(root);

                try (OutputStream target =
                             ops.openOutput(staged)) {
                    byteCount = copyBounded(source, target);
                }
            }

            // Only publish after BOTH streams closed successfully.
            ops.move(staged, root.resolve(id));
            promoted = true;
            return new StoredDocument(id, byteCount);

        } catch (IOException | RuntimeException error) {
            primary = error;
            throw error;

        } finally {
            if (staged != null && !promoted) {
                try {
                    ops.deleteIfExists(staged);
                } catch (IOException cleanupError) {
                    if (primary != null) {
                        primary.addSuppressed(cleanupError);
                    } else {
                        throw cleanupError;
                    }
                }
            }
        }
    }

    public byte[] readBytes(String id) throws IOException {
        if (id == null
                || !DOCUMENT_ID.matcher(id).matches()) {
            throw new InvalidDocumentIdException();
        }

        Path path = root.resolve(id);

        try (InputStream source = ops.openInput(path);
             ByteArrayOutputStream result =
                     new ByteArrayOutputStream()) {
            try {
                copyBounded(source, result);
            } catch (FileTooLargeException tooLarge) {
                throw new IOException(
                        "Stored data exceeds read safety limit",
                        tooLarge);
            }
            return result.toByteArray();
        }
    }

    private long copyBounded(
            InputStream source, OutputStream target)
            throws IOException {

        byte[] buffer = new byte[8192];
        long count = 0L;
        int amount;

        while ((amount = source.read(buffer)) != -1) {
            if (amount == 0) {
                throw new IOException(
                        "Unexpected zero-length read");
            }

            if (amount > maxBytes - count) {
                throw new FileTooLargeException(
                        "File exceeds configured size limit");
            }

            target.write(buffer, 0, amount);
            count += amount;
        }

        return count;
    }
}
```

**Quan trọng:** Đây là file Java đầy đủ. `java.time.Duration` import trong ví dụ trên không được sử dụng; Java cho phép import thừa (chỉ làm IDE/linter cảnh báo), không ảnh hưởng compile. Một project production nên xóa import thừa này theo Checkstyle/Spotless rule. Logic cố ý đơn giản để nhìn rõ **ownership, resource close và cleanup**.

### 15.1. Trình tự thành công

1. `save` nhận ownership của InputStream.
2. `createDirectories` chuẩn bị thư mục.
3. `createTempFile` trả một Path thuộc root.
4. `openOutput` mở staging file.
5. `copyBounded` copy tối đa `maxBytes`.
6. `target.close()` từ try-with-resources; nếu lỗi, nhảy vào nhánh failure.
7. `source.close()` từ try-with-resources; nếu lỗi, cũng failure.
8. `ops.move(staged, root.resolve(id))` publish.
9. `promoted=true`, trả generated ID và số bytes.
10. `finally` **không xóa file đã publish**.

### 15.2. Trình tự thất bại

Nếu mkdir/create/read/write/close/move fail:

- Input stream được thử close khi đã vào `try(InputStream source=input)`.
- Output stream được thử close nếu đã mở.
- `staged` tồn tại → `deleteIfExists` được gọi.
- Nếu delete cũng fail, lỗi delete được thêm vào `error.getSuppressed()`.
- Không trả `StoredDocument`/HTTP 201.
- File đích generated không được công bố nếu promotion chưa xác nhận.

**Giới hạn phải nêu thật:** OS/filesystem crash, move kết thúc không rõ trạng thái, durability/fsync và process kill không thể được “chứng minh” chỉ qua `finally`. Nếu data rất quan trọng, cần storage transaction/outbox/idempotency, atomic move khi được hỗ trợ, và recovery janitor riêng.

### 15.3. Đọc file: input stream thuộc về ai?

`readBytes` mở InputStream rồi **đọc hết vào RAM trong giới hạn `maxBytes`** và đóng stream trước khi trả `byte[]`. Đây là lựa chọn demo cho payload ≤1 MiB. Với file hàng GB, không đọc toàn bộ vào RAM: dùng streaming response với trách nhiệm đóng resource rõ ràng, test client disconnect, backpressure và servlet lifecycle.

### 15.4. Vì sao validate ID thay vì dùng originalFilename?

File cuối dùng UUID server tạo, và `readBytes` chỉ chấp nhận đúng dạng `UUID.bin`. Chuỗi `../../secrets`, slash, backslash và filename do caller cung cấp không thể biến thành đường dẫn ngoài root. Tuy nhiên, **name validation không bảo vệ mọi symlink race** nếu actor khác có thể tạo symlink ngay dưới root: cần bảo vệ quyền trên directory và cơ chế open phù hợp ở production.

## 16. Cấu hình Spring bean và upload limit

**`src/main/java/com/example/ioresource/StoreConfiguration.java`**

```java
package com.example.ioresource;

import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StoreConfiguration {

    @Bean
    LocalDocumentStore localDocumentStore(
            StorageOps ops,
            @Value("${demo.storage.root:./build/io-store}")
                    String root,
            @Value("${demo.storage.max-bytes:1048576}")
                    long maxBytes) {

        return new LocalDocumentStore(
                Path.of(root), ops, maxBytes);
    }
}
```

`demo.storage.root` chỉ nên trỏ vào **application-owned, isolated directory**. Giá trị mặc định `./build/io-store` thích hợp cho demo, không phải cấu hình production. `demo.storage.max-bytes=1048576` là **1 MiB ở storage layer**, bên cạnh limits của multipart parser/proxy:

```properties
# Ví dụ giới hạn multipart parser, không thay thế maxBytes của store.
spring.servlet.multipart.max-file-size=5MB
spring.servlet.multipart.max-request-size=6MB
demo.storage.max-bytes=1048576
```

Lưu ý: `MockMvc.multipart(...)` không chạy servlet container parser thực, nên không dùng một MockMvc test để kết luận cấu hình `spring.servlet.multipart.max-file-size` chặn bytes đúng trên TCP. Test storage bound trực tiếp; muốn kiểm servlet parser limit, cần integration qua server thật.

## 17. HTTP controller và response contract

**`src/main/java/com/example/ioresource/DocumentController.java`**

```java
package com.example.ioresource;

import java.io.IOException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/documents")
public class DocumentController {

    private final LocalDocumentStore store;

    public DocumentController(LocalDocumentStore store) {
        this.store = store;
    }

    @PostMapping(
            consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<StoredDocument> upload(
            @RequestPart("file") MultipartFile file)
            throws IOException {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(store.save(file.getInputStream()));
    }

    @GetMapping(
            path = "/{id}",
            produces = MediaType.APPLICATION_OCTET_STREAM_VALUE)
    public ResponseEntity<byte[]> download(
            @PathVariable String id) throws IOException {

        return ResponseEntity.ok()
                .contentType(
                        MediaType.APPLICATION_OCTET_STREAM)
                .body(store.readBytes(id));
    }
}
```

**Controller không gọi `close` lần thứ hai** vì `store.save` đã nhận ownership của stream. Nếu controller và storage cùng close một non-idempotent resource, có thể gây lỗi/trạng thái khó hiểu. Với `MultipartFile.transferTo(Path)` thay vì InputStream, quyền sở hữu/cleanup khác: phải đọc javadoc của API được dùng; controller/servlet temp files vẫn do multipart resolver/container quản lý.

Khi upload fail, controller không trả 201. Khi download ID sai, store ném `InvalidDocumentIdException`; khi file không tồn tại, NIO ném `NoSuchFileException`; khi OS denial/IO fail, advice map lỗi phù hợp.

## 18. Error advice: không đưa đường dẫn OS ra response

**`src/main/java/com/example/ioresource/StorageErrorAdvice.java`**

```java
package com.example.ioresource;

import java.io.IOException;
import java.nio.file.NoSuchFileException;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class StorageErrorAdvice {

    public record ErrorPayload(String code) {
    }

    @ExceptionHandler(InvalidDocumentIdException.class)
    ResponseEntity<ErrorPayload> invalidId() {
        return ResponseEntity.badRequest()
                .body(new ErrorPayload("INVALID_ID"));
    }

    @ExceptionHandler(NoSuchFileException.class)
    ResponseEntity<ErrorPayload> missingFile() {
        return ResponseEntity.status(404)
                .body(new ErrorPayload("NOT_FOUND"));
    }

    @ExceptionHandler(FileTooLargeException.class)
    ResponseEntity<ErrorPayload> tooLarge() {
        return ResponseEntity.status(413)
                .body(new ErrorPayload("TOO_LARGE"));
    }

    @ExceptionHandler(IOException.class)
    ResponseEntity<ErrorPayload> ioError() {
        return ResponseEntity.status(500)
                .body(new ErrorPayload("STORAGE_FAILURE"));
    }
}
```

Spring MVC chọn handler cho exception type cụ thể trước generic IOException. `AccessDeniedException` từ NIO là IOException nên map 500 trong demo, không bị nhầm là Spring Security authorization denial 403.

**Hậu quả cần test:** Request chứa đường dẫn như `/srv/private/invoices` trong exception message không được lộ vào JSON. Trên server, logs có thể chứa stack trace được kiểm soát bởi logging policy và không tiết lộ keys/tokens; trong test response chỉ có `code`.

**Không coi handler chung IOException là xử lý mọi lỗi HTTP:** Một request client ngắt kết nối khi servlet đang ghi response có thể xảy ra sau khi headers đã commit; advice không thể chắc chắn tạo lại response 500. Backend read/streaming file lớn cần test behavior riêng.

## 19. JUnit `@TempDir`: kiểm file thật mà không đụng workspace

JUnit Jupiter có:

```java
@TempDir
Path tempDirectory;
```

Extension tạo một thư mục dành riêng cho test/test lifecycle tương ứng, có cleanup do JUnit quản lý. Nó tốt hơn hard-code `/tmp/test.txt` vì:

- Không collision giữa nhiều tests chạy song song.
- Không phá file của người dùng/production.
- Không phụ thuộc working directory và tên volume.
- Có thể inspect chính xác staging/final files.
- Khi test fail, JUnit vẫn cố cleanup directory tùy cấu hình lifecycle.
- Làm test dễ chạy trên Windows/macOS/Linux.

**Không dùng `@TempDir` để test permission denial bằng `chmod` mặc định.** Test permission branch bằng spy hoặc test OS-specific có assumptions. Và **không gọi `Files.walk(root).forEach(delete)` vô tội vạ** trên path lấy từ external input: chỉ xóa exact test-owned directory.

### 19.1. `Files.list` cũng cần đóng

Trong test:

```java
try (Stream<Path> entries = Files.list(root)) {
    assertEquals(0L, entries.count());
}
```

`Files.list` trả `Stream<Path>` gắn với directory resources; stream phải được close. Tương tự `Files.walk` và `Files.lines` cũng phải được đóng để tránh handle leak hoặc Windows không xóa được directory sau test.

## 20. Store tests: happy path và lỗi với Mockito spy

**`src/test/java/com/example/ioresource/LocalDocumentStoreTest.java`**

```java
package com.example.ioresource;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AccessDeniedException;
import java.nio.file.Files;
import java.nio.file.NoSuchFileException;
import java.nio.file.Path;
import java.util.stream.Stream;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.spy;

class LocalDocumentStoreTest {

    @TempDir
    Path root;

    private NioStorageOps ops;
    private LocalDocumentStore store;

    @BeforeEach
    void setUp() {
        ops = spy(new NioStorageOps());
        store = new LocalDocumentStore(root, ops, 8);
    }

    @Test
    void savesAndReadsBytesWithoutLeftoverStage()
            throws Exception {

        byte[] bytes = "abc".getBytes(StandardCharsets.UTF_8);
        TrackedInput input = new TrackedInput(bytes);

        StoredDocument saved = store.save(input);

        assertTrue(input.closed);
        assertEquals(3L, saved.bytes());
        assertTrue(Files.exists(root.resolve(saved.id())));
        assertArrayEquals(bytes, store.readBytes(saved.id()));
        assertEquals(1L, fileCount());
    }

    @Test
    void overLimitFailsAndDeletesStaging()
            throws Exception {

        TrackedInput input = new TrackedInput(
                "123456789".getBytes(StandardCharsets.UTF_8));

        assertThrows(FileTooLargeException.class,
                () -> store.save(input));

        assertTrue(input.closed);
        assertEquals(0L, fileCount());
    }

    @Test
    void readErrorStillClosesInputAndDeletesStage()
            throws Exception {

        FailingReadInput input = new FailingReadInput();

        IOException error = assertThrows(
                IOException.class,
                () -> store.save(input));

        assertEquals("read failed", error.getMessage());
        assertTrue(input.closed);
        assertEquals(0L, fileCount());
    }

    @Test
    void writeErrorClosesInputAndDeletesStage()
            throws Exception {

        OutputStream brokenOutput = new OutputStream() {
            @Override
            public void write(int value) throws IOException {
                throw new IOException("disk write failed");
            }
        };

        doReturn(brokenOutput).when(ops)
                .openOutput(any(Path.class));

        TrackedInput input = new TrackedInput(
                "abc".getBytes(StandardCharsets.UTF_8));

        IOException error = assertThrows(
                IOException.class,
                () -> store.save(input));

        assertEquals("disk write failed", error.getMessage());
        assertTrue(input.closed);
        assertEquals(0L, fileCount());
    }

    @Test
    void directoryPermissionErrorStillClosesInput()
            throws Exception {

        doThrow(new AccessDeniedException("blocked-root"))
                .when(ops).createDirectories(root);

        TrackedInput input = new TrackedInput(
                "abc".getBytes(StandardCharsets.UTF_8));

        assertThrows(AccessDeniedException.class,
                () -> store.save(input));

        assertTrue(input.closed);
        assertEquals(0L, fileCount());
    }

    @Test
    void cannotOpenStageOutputLeavesNoStage()
            throws Exception {

        doThrow(new AccessDeniedException("blocked-file"))
                .when(ops).openOutput(any(Path.class));

        TrackedInput input = new TrackedInput(
                "abc".getBytes(StandardCharsets.UTF_8));

        assertThrows(AccessDeniedException.class,
                () -> store.save(input));

        assertTrue(input.closed);
        assertEquals(0L, fileCount());
    }

    @Test
    void moveAccessDeniedDeletesUnpromotedStage()
            throws Exception {

        doThrow(new AccessDeniedException("rename blocked"))
                .when(ops).move(
                        any(Path.class), any(Path.class));

        TrackedInput input = new TrackedInput(
                "abc".getBytes(StandardCharsets.UTF_8));

        assertThrows(AccessDeniedException.class,
                () -> store.save(input));

        assertTrue(input.closed);
        assertEquals(0L, fileCount());
    }

    @Test
    void cleanupFailureIsSuppressedOnOriginalMoveError()
            throws Exception {

        doThrow(new IOException("move failed"))
                .when(ops).move(
                        any(Path.class), any(Path.class));
        doThrow(new IOException("delete failed"))
                .when(ops).deleteIfExists(any(Path.class));

        IOException error = assertThrows(
                IOException.class,
                () -> store.save(new ByteArrayInputStream(
                        "abc".getBytes(StandardCharsets.UTF_8))));

        assertEquals("move failed", error.getMessage());
        assertEquals(1, error.getSuppressed().length);
        assertEquals(
                "delete failed",
                error.getSuppressed()[0].getMessage());
        // The intentional failed cleanup leaves a .part file.
        // @TempDir extension owns this isolated test directory.
    }

    @Test
    void sourceCloseFailureHappensBeforePublish()
            throws Exception {

        InputStream closeFails =
                new ByteArrayInputStream(
                        "abc".getBytes(StandardCharsets.UTF_8)) {
                    @Override
                    public void close() throws IOException {
                        super.close();
                        throw new IOException("input close failed");
                    }
                };

        IOException error = assertThrows(
                IOException.class,
                () -> store.save(closeFails));

        assertEquals("input close failed", error.getMessage());
        assertEquals(0L, fileCount());
    }

    @Test
    void invalidIdCannotEscapeStoreRoot()
            throws Exception {

        assertThrows(InvalidDocumentIdException.class,
                () -> store.readBytes("../secrets.txt"));
        assertEquals(0L, fileCount());
    }

    @Test
    void absentDocumentReturnsNoSuchFile()
            throws Exception {

        String validButUnknown =
                "00000000-0000-0000-0000-000000000000.bin";

        assertThrows(NoSuchFileException.class,
                () -> store.readBytes(validButUnknown));
    }

    @Test
    void failingDownloadReadClosesOpenedStream()
            throws Exception {

        StoredDocument saved = store.save(
                new ByteArrayInputStream(
                        "abc".getBytes(StandardCharsets.UTF_8)));
        FailingReadInput faulty = new FailingReadInput();

        doReturn(faulty).when(ops).openInput(
                root.resolve(saved.id()));

        assertThrows(IOException.class,
                () -> store.readBytes(saved.id()));

        assertTrue(faulty.closed);
        assertTrue(Files.exists(root.resolve(saved.id())));
    }

    private long fileCount() throws IOException {
        try (Stream<Path> files = Files.list(root)) {
            return files.count();
        }
    }

    private static final class TrackedInput
            extends ByteArrayInputStream {

        boolean closed;

        TrackedInput(byte[] bytes) {
            super(bytes);
        }

        @Override
        public void close() throws IOException {
            closed = true;
            super.close();
        }
    }

    private static final class FailingReadInput
            extends InputStream {

        private boolean first = true;
        boolean closed;

        @Override
        public int read() throws IOException {
            if (first) {
                first = false;
                return 'A';
            }
            throw new IOException("read failed");
        }

        @Override
        public void close() {
            closed = true;
        }
    }
}
```

**Có 12 test methods** trong lớp này. Chúng kiểm filesystem thật trong `@TempDir`, rồi mô phỏng exceptions qua Mockito spy của NioStorageOps. Các tests không sửa POSIX permissions hoặc đòi CI phải chạy bằng quyền cụ thể.

### 20.1. Tại sao test write failure không cần disk thật bị đầy?

Nếu cố tạo file nhiều GB để kích hoạt `ENOSPC`, CI có thể hỏng, chạy rất lâu hoặc ảnh hưởng người khác. Trong `writeErrorClosesInputAndDeletesStage`, spy trả OutputStream luôn ném `IOException("disk write failed")`. File staging vẫn được tạo thực, nên test chứng minh cleanup trên filesystem, không phải lý do OS chính xác. Test disk-full/volume quota riêng mới kiểm Linux/volume behavior.

### 20.2. Tại sao permission tests dùng `doThrow`?

`doThrow(new AccessDeniedException(...))` đảm bảo nhánh lỗi xảy ra bất kể Windows ACL, POSIX mode bits, Docker user hoặc việc chạy dưới root. Unit test bảo vệ **phản ứng của ứng dụng** trước lỗi. Muốn chứng minh application deployment có quyền đúng trên PVC/NFS/S3, cần một integration test trên môi trường đó.

### 20.3. Nhánh cleanup fail chứng minh điều gì?

Khi `move` ném IOException và delete staging cũng ném IOException, code giữ **move failed** làm lỗi chính và **delete failed** trong suppressed. Nếu chỉ catch + ignore lỗi delete, hệ thống có thể âm thầm tích lũy temp files. Một production janitor cần alert/quota/retention và có thể dùng retry hợp lý, không xóa arbitrary files.

### 20.4. Stream ownership được xác minh ra sao?

`TrackedInput.closed` được bật trong `close()`. Các tests kiểm true cả khi mkdir/write/move gặp lỗi. Một test chỉ kiểm fileCount bằng 0 mà không kiểm `closed` có thể bỏ sót file descriptor leak trên Windows; một test chỉ kiểm closed mà không kiểm staging cũng có thể bỏ sót partial output.

## 21. MVC slice: kiểm HTTP status và response không lộ path

**`src/test/java/com/example/ioresource/DocumentControllerTest.java`**

```java
package com.example.ioresource;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.AccessDeniedException;
import java.nio.file.NoSuchFileException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.containsString;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(DocumentController.class)
@Import(StorageErrorAdvice.class)
class DocumentControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    LocalDocumentStore store;

    @Test
    void validMultipartMapsToCreatedResponse()
            throws Exception {

        MockMultipartFile file = new MockMultipartFile(
                "file", "../../untrusted-name.txt",
                "text/plain",
                "abc".getBytes(StandardCharsets.UTF_8));

        when(store.save(any(InputStream.class)))
                .thenReturn(new StoredDocument(
                        "11111111-1111-4111-8111-111111111111.bin",
                        3));

        mvc.perform(multipart("/api/documents").file(file))
                .andExpectAll(
                        status().isCreated(),
                        jsonPath("$.bytes").value(3),
                        jsonPath("$.id").value(
                                "11111111-1111-4111-8111-111111111111.bin"));

        verify(store).save(any(InputStream.class));
        // Controller does not use original filename as storage path.
    }

    @Test
    void noSuchDocumentMapsTo404WithoutRawPath()
            throws Exception {

        String id =
                "00000000-0000-0000-0000-000000000000.bin";

        when(store.readBytes(id))
                .thenThrow(new NoSuchFileException(
                        "/srv/private/missing.bin"));

        mvc.perform(get("/api/documents/{id}", id))
                .andExpectAll(
                        status().isNotFound(),
                        jsonPath("$.code").value("NOT_FOUND"),
                        content().string(
                                not(containsString("/srv/private"))));
    }

    @Test
    void storagePermissionDeniedIsServerErrorNotAuth403()
            throws Exception {

        MockMultipartFile file = new MockMultipartFile(
                "file", "data.bin",
                "application/octet-stream",
                new byte[] {1, 2});

        when(store.save(any(InputStream.class)))
                .thenThrow(new AccessDeniedException(
                        "/srv/private/upload-root"));

        mvc.perform(multipart("/api/documents").file(file))
                .andExpectAll(
                        status().isInternalServerError(),
                        jsonPath("$.code").value("STORAGE_FAILURE"),
                        content().string(
                                not(containsString("/srv/private"))));
    }

    @Test
    void oversizedPayloadIs413WithNeutralCode()
            throws Exception {

        MockMultipartFile file = new MockMultipartFile(
                "file", "huge.bin",
                "application/octet-stream",
                new byte[] {1, 2});

        when(store.save(any(InputStream.class)))
                .thenThrow(new FileTooLargeException(
                        "secret storage limit path"));

        mvc.perform(multipart("/api/documents").file(file))
                .andExpectAll(
                        status().is(413),
                        jsonPath("$.code").value("TOO_LARGE"),
                        content().string(
                                not(containsString("secret storage"))));
    }
}
```

**Có 4 test methods.** `@WebMvcTest` dùng controller thật và mocked LocalDocumentStore, nên kiểm mapping multipart request và exception handler ở MVC layer. Nó không kiểm NIO cleanup — việc đó do `LocalDocumentStoreTest` làm. Đồng thời **MockMultipartFile** nằm trong bộ nhớ, không phải multipart parser TCP thật.

Lỗi 403 từ Spring Security (nếu sau này bổ sung) phải có test riêng; ở bài này `AccessDeniedException` của filesystem được map 500 để tránh làm người dùng hiểu lầm đó là lỗi phân quyền HTTP.

## 22. Full Spring context với NIO thật và MockMvc

**`src/test/java/com/example/ioresource/DocumentIntegrationTest.java`**

```java
package com.example.ioresource;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "demo.storage.max-bytes=1048576",
        "spring.servlet.multipart.max-file-size=5MB",
        "spring.servlet.multipart.max-request-size=6MB"
})
@AutoConfigureMockMvc
class DocumentIntegrationTest {

    @TempDir
    static Path root;

    @DynamicPropertySource
    static void storageDirectory(DynamicPropertyRegistry registry) {
        registry.add(
                "demo.storage.root", () -> root.toString());
    }

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void realNioStoreRoundTripsUploadedDocument()
            throws Exception {

        byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);
        MockMultipartFile file = new MockMultipartFile(
                "file", "../../not-a-path.txt",
                "text/plain", bytes);

        MvcResult created = mvc.perform(
                multipart("/api/documents").file(file))
                .andExpectAll(
                        status().isCreated(),
                        jsonPath("$.bytes").value(5))
                .andReturn();

        String id = objectMapper.readTree(
                created.getResponse().getContentAsString())
                .get("id").asText();

        assertTrue(Files.exists(root.resolve(id)));

        mvc.perform(get("/api/documents/{id}", id))
                .andExpectAll(
                        status().isOk(),
                        content().bytes(bytes));

        try (Stream<Path> paths = Files.list(root)) {
            assertEquals(
                    0L,
                    paths.filter(p -> p.getFileName()
                            .toString().endsWith(".part")).count());
        }
    }

    @Test
    void storeRejectsPayloadOverOneMib()
            throws Exception {

        byte[] bytes = new byte[1048577];
        MockMultipartFile file = new MockMultipartFile(
                "file", "large.bin",
                "application/octet-stream", bytes);

        mvc.perform(multipart("/api/documents").file(file))
                .andExpectAll(
                        status().is(413),
                        jsonPath("$.code").value("TOO_LARGE"));
    }

    @Test
    void malformedIdIs400RatherThanRawFilesystemLookup()
            throws Exception {

        mvc.perform(get("/api/documents/{id}", "bad_id"))
                .andExpectAll(
                        status().isBadRequest(),
                        jsonPath("$.code").value("INVALID_ID"));
    }
}
```

**Có 3 test methods.** Test full context dùng NIO adapter thật, bean config thật và real files trong `@TempDir` nhưng `MockMvc` vẫn không mở socket. Nó chứng minh controller/store wiring, staging cleanup trong happy path và giới hạn 1 MiB ở **storage layer**, không chứng minh reverse proxy/servlet multipart parser thực hiện limit như production.

**Lưu ý JUnit/Context cache:** `@TempDir static Path root` có lifecycle của test class, còn `@DynamicPropertySource` cung cấp đường dẫn lúc Spring context tạo bean. Nếu nhiều test classes chia sẻ một cached context nhưng mỗi class có static @TempDir khác, DataSource/file-store có thể trỏ đến temp directory đã bị JUnit xóa. Bài demo chỉ có **một class** dùng cấu hình này; project thực nên dùng unique dynamic config/context isolation hoặc một test-owned directory có lifecycle khớp với cached context.

## 23. Tóm tắt số tests và cách chạy

| Test class | Số `@Test` | Trọng tâm |
|---|---:|---|
| `LocalDocumentStoreTest` | 12 | Read/write/move/permission/close/cleanup và suppressed exceptions |
| `DocumentControllerTest` | 4 | HTTP status, 413/404/500 và error redaction |
| `DocumentIntegrationTest` | 3 | Wiring Spring + NIO thật, multipart mock và readback |
| **Tổng** | **19** | IO failure paths + stream ownership + resource cleanup |

Chạy:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Kết quả **dự kiến** khi build/dependencies/Java 17 phù hợp: `BUILD SUCCESSFUL`. JUnit report thường tại `build/reports/tests/test/index.html`. **Tôi chưa chạy Gradle/JUnit trên repository thực tế**, nên đây là expected outcome từ kiểm tra source/APIs, không phải test execution report.

Không có stdout business cố định. Tên UUID, temp file, filesystem path và thứ tự test methods là ngẫu nhiên/không được assert. Nhánh lỗi chủ động được mô phỏng qua Mockito, vì vậy output error code/staging state ổn định hơn so với cố gây disk-full hoặc permission denial trên CI.

## 24. Test matrix: từng failure phải có hậu điều kiện

| Failure | Input closed? | Output closed? | Stage removed? | Final visible? | API result |
|---|---|---|---|---|---|
| Success | Có | Có | Stage move khỏi tên cũ | Có | 201 |
| Directory create denied | Có | Chưa mở | Không tạo stage | Không | 500 |
| Temp file create denied | Có | Chưa mở | Không tạo stage | Không | 500 |
| Output open denied | Có | Không mở thành công | Có attempt cleanup | Không | 500 |
| Read IOException | Có | Có attempt close | Có attempt cleanup | Không | 500 |
| Write IOException | Có | Có attempt close | Có attempt cleanup | Không | 500 |
| Input close IOException | Có attempt close | Đã close | Có attempt cleanup | Không | 500 |
| Output close IOException | Có attempt close | Có attempt close | Có attempt cleanup | Không | 500 |
| Move AccessDeniedException | Có | Có | Có attempt cleanup | Không xác nhận publish | 500 |
| Cleanup IOException | Có | Theo lỗi gốc | **Có attempt, nhưng có thể còn file** | Không xác nhận publish | 500 + suppressed |
| Payload over limit | Có | Có attempt close | Có attempt cleanup | Không | 413 |
| Download file absent | Không mở thành công | N/A | N/A | Không | 404 |
| Download read IOException | Có attempt close | ByteArrayOutputStream close | N/A | File đã có vẫn tồn tại | 500 |
| Invalid document ID | Không mở | N/A | Không | Không | 400 |

**Phân biệt “được thử đóng” với “đã đóng thành công”.** Nếu chính `close()` ném exception, test không thể khẳng định underlying OS handle đã giải phóng hoàn toàn; cần diagnostics/metrics hoặc provider-specific checks. Tương tự, delete thất bại thì không được báo “stage removed”; test phải thấy suppressed và production phải có cleanup/recovery policy.

## 25. Một lỗi quan trọng: close failure sau khi publish

Phản ví dụ:

```java
try (InputStream input = requestInput) {
    Files.copy(input, tempPath);
    Files.move(tempPath, finalPath);
    return success();
}
// InputStream.close() chỉ chạy sau khi final file đã move.
```

Nếu `InputStream.close()` ném IOException, method trả lỗi dù file đã publish. Client retry có thể tạo duplicate document. Demo đóng **cả source và output trước `ops.move`**:

```text
try (InputStream) {
    try (OutputStream) { copy(); }
}
move(staging, final);
return success;
```

Đây là một sự khác biệt nhỏ về dấu ngoặc nhưng có ý nghĩa về **external observable state**. Test `sourceCloseFailureHappensBeforePublish` xác minh close failure làm staging bị xóa, không tạo final file.

**Lưu ý:** Không thể biến file system thành transaction hoàn hảo chỉ bằng thay vị trí close. Move có thể thất bại sau một trạng thái không xác định, app có thể bị kill ở mọi điểm. Nếu caller retry được, cần idempotency key/object registry/compensation policy và checkpoint durable.

## 26. Khi nào nên dùng `Files.move(..., ATOMIC_MOVE)`?

`StandardCopyOption.ATOMIC_MOVE` yêu cầu filesystem thực hiện move như một atomic filesystem operation, nhưng **không phải provider nào cũng hỗ trợ**, nhất là cross-filesystem. API có thể ném `AtomicMoveNotSupportedException`. Nếu một requirement yêu cầu “reader không bao giờ thấy half-published file”, production nên:

- Tạo staging cùng filesystem với final.
- Move với `ATOMIC_MOVE`.
- Nếu unsupported, **fail theo policy** thay vì fallback âm thầm.
- Không dùng `REPLACE_EXISTING` khi không được phép overwrite.
- Kiểm duplicate destination IDs/collision.
- Xem tài liệu provider về semantics khi destination đã tồn tại.
- Cân nhắc `FileChannel.force(true)` và directory fsync nếu cần durability khi power failure (tùy OS/provider).
- Với object storage, không giả định rename atomic; dùng multipart completion/metadata publish contract riêng.

**`ATOMIC_MOVE` không tự bảo đảm durable sau crash** hoặc exactly-once request semantics. Test MockOps có thể xác nhận đúng options được gọi; test filesystem thật phải chạy trên provider cần support. Bài demo chọn `Files.move` portable để tập trung vào error handling/cleanup, không tuyên bố production durability.

## 27. Đọc stream trong Spring MVC và ownership

Khi controller trả `byte[]`, Spring MVC đã có bytes trong RAM và method `LocalDocumentStore.readBytes` đóng input trước khi response serialization. Với file lớn, thường trả `Resource` hoặc `StreamingResponseBody`:

```java
// Snippet: không phải file runnable độc lập.
// StreamingResponseBody cần lifecycle/error management theo framework.
StreamingResponseBody body = out -> {
    try (InputStream in = storage.openOwnedStream(id)) {
        in.transferTo(out);
    }
};
```

Ở đây `out` thuộc servlet response, **không tự close** nếu framework quản lý nó. InputStream thuộc storage adapter phải close sau copy. Nếu client disconnect khi streaming, IOException có thể xảy ra sau khi HTTP headers đã được commit; không thể đổi response thành JSON 500 dễ dàng. Test cần simulate response write failure, early disconnect và cleanup đúng boundary.

### 27.1. `InputStreamResource` là một-shot

`InputStreamResource` thường đại diện cho **một stream đã mở**, không phải tài nguyên có thể đọc lặp tùy ý. Nếu framework/test gọi `contentLength()` hoặc đọc hai lần tùy đường code, có nguy cơ consume stream. Với file đã lưu trên disk, `PathResource` hoặc một Resource với khả năng mở stream mới có thể thích hợp hơn. Nhưng đừng trao toàn quyền đọc arbitrary filesystem paths cho caller; vẫn phải validate ID/authorization và gắn đúng lifecycle.

## 28. Path traversal, symlinks và filesystem trust boundary

Một request:

```http
POST /api/documents
filename="../../application.yml"
```

không được khiến server viết ngoài root. Demo không dùng originalFilename trong đường dẫn, mà sinh `UUID.bin`; GET chỉ nhận ID theo regex cứng. Nhưng production còn những rủi ro:

- Dùng `resolve(userInput)` rồi chỉ gọi `normalize` chưa đủ để ngăn mọi symlink traversal.
- Một symlink trong root có thể trỏ ngoài root ngay cả khi tên file hợp lệ.
- Time-of-check/time-of-use (TOCTOU): kiểm `exists/isReadable` rồi mở sau có thể bị đổi entry giữa hai bước.
- Path canonicalization trên Windows (drive letters, UNC, reserved device names) khác POSIX.
- Case-insensitive filesystem và Unicode normalization có thể tạo collision.
- Temporary directory shared world-writable có nguy cơ race nếu filename predictable.
- Zip Slip khi extract archive entry names cũng là path traversal.
- ACL root phải chặn untrusted users/processes thay contents.
- Nếu đọc file theo tenant, phải có application-level ownership authorization trước NIO open.

**Không dùng regex UUID như một security substitute cho OS ACL**. Cấu hình production cần root private, permissions/ownership chính xác, no-follow strategy khi có attacker, network egress/storage policy và audit.

## 29. Disk full, quota, partial writes và durability

Lỗi disk full có thể hiện ra khi:

- `Files.createTempFile` không tạo được entry.
- `OutputStream.write` ném IOException sau khi đã ghi một phần.
- `flush()/close()` báo lỗi muộn.
- `Files.move` thất bại do filesystem/provider state.
- Một process khác dùng hết quota ngay sau khi bạn check free space.

**Đừng dùng `Files.getFileStore(...).getUsableSpace()` như bảo đảm đủ dung lượng**; đó là giá trị tại một thời điểm, vẫn có race và quota. Hãy enforce application upload limit trước/đang copy, theo dõi disk usage, và xử lý IOException thực. Test injection cho disk-full tốt hơn tự tạo file khổng lồ trong CI; volume quota tests được chạy cô lập trên môi trường chuyên dụng.

**Durability:** Đóng stream không đồng nghĩa bytes đã được fsync xuống thiết bị. Hệ thống yêu cầu chắc chắn sau power loss phải có hợp đồng durability với filesystem/object storage và integration tests tương ứng. Một test `@TempDir` ghi rồi đọc lại ngay chỉ chứng minh dữ liệu thấy được trong cùng runtime, chưa chứng minh survive crash.

## 30. Concurrency, duplicate names và retries

Một client timeout sau khi server đã publish file nhưng trước khi client nhận `201`. Client retry cùng upload có thể tạo **hai UUID files**, dù mỗi lần save là thành công riêng. Nếu contract không chấp nhận duplicates:

- Nhận idempotency key theo phạm vi caller/operation.
- Ghi registry ánh xạ key → object status/result bằng transaction phù hợp.
- Định nghĩa các trạng thái `UPLOADING`, `COMMITTED`, `FAILED`.
- Cleanup stages mồ côi theo TTL nhưng không xóa request đang hoạt động.
- Tránh race hai requests cùng key và publish hai objects.
- Nếu có DB record + file, cần outbox/saga/compensation; filesystem move không cùng transaction với JDBC.
- Không dùng `synchronized` một JVM như giải pháp cho nhiều replicas.

**Tên UUID không phải cơ chế idempotency.** Nó chỉ giảm collision. Dù FileStore demo không overwrite đối tượng có tên khác, request retry vẫn có thể tạo bản sao về mặt business.

## 31. Resource cleanup khi app crash

`try-with-resources` chạy khi control flow Java thoát scope, nhưng không bảo đảm `finally` chạy nếu process bị kill hoặc host mất điện. Các artifact có thể tồn tại:

```text
root/
  .upload-442211.part        <- incomplete stage mồ côi
  1960c74d-... .bin         <- đã publish
  .upload-667788.part        <- đang được request live sử dụng
```

Một janitor **không được xóa mọi `.part` ngay lập tức**, vì có thể xóa stage của một upload đang diễn ra. Phải có ownership/age threshold, upload lease hoặc process coordination, và chỉ quét directory app thực sự sở hữu. Khi dùng multiple pods trên một shared PVC, janitor cần distributed lock/lease hoặc metadata để không phá nhau.

Với object storage, multipart uploads có thể để lại parts bị tính phí; cần lifecycle policy/abort incomplete multipart upload và audit. Với temporary servlet uploads, container cũng có cleanup riêng nhưng không nên phụ thuộc nó để xóa app staging files.

## 32. File locks và Windows-specific failure

Windows thường nhạy hơn với file handles chưa đóng: một file có thể không đổi tên/xóa được khi stream còn mở hoặc antivirus đang scan. Linux/POSIX có thể cho unlink một file đang mở, nên một test “xóa được file” trên Linux không chứng minh handles đã close.

Các cách kiểm:

- Dùng `TrackedInput.closed`/instrumented OutputStream tại unit layer.
- Dùng `@TempDir` để giữ scope file riêng.
- Test real lock behavior trên Windows runner khi sản phẩm hỗ trợ Windows.
- Retry transient lock trong giới hạn, có backoff và idempotency, không retry mọi AccessDeniedException vô hạn.
- Không bỏ qua failed cleanup chỉ vì Linux đã cho unlink.
- Đóng `Files.list`/`Files.walk` streams để JUnit @TempDir cleanup không bị cản.

**Một kiểm thử cross-platform tốt nên tránh assert exact OS error messages**. `AccessDeniedException.getMessage()` có thể khác nhau theo provider/locale/path. Test exception type/contract, không hard-code nguyên message trừ khi chính test cố tình ném một message.

## 33. NIO permissions và giả lập cross-platform

Nếu sản phẩm cần kiểm POSIX permissions thực:

```java
// Snippet chạy trên POSIX runner có hỗ trợ attribute view.
// Không chạy mặc định trên Windows hoặc CI root.
Assumptions.assumeTrue(Files.getFileStore(dir)
        .supportsFileAttributeView("posix"));
Files.setPosixFilePermissions(
        dir, PosixFilePermissions.fromString("r--------"));
```

Đây là **snippet**, không nằm trong test demo; còn cần import `Assumptions`, `Files`, `PosixFilePermissions` và khôi phục permission trong `finally` trước khi @TempDir cleanup. Ngay trên POSIX, process đặc quyền có thể vẫn truy cập. Do đó một test robust sẽ thêm assumptions về effective UID/permissions hoặc dùng container non-root riêng.

Với Windows ACL, cần `AclFileAttributeView` và test runner Windows chuyên biệt. Không cố ép cùng test chmod chạy trên mọi OS.

## 34. Giao tiếp với cloud object storage và remote IO

Nguyên tắc đóng stream/cleanup áp dụng cho S3/GCS/Azure Blob, nhưng API thực có semantics khác:

- Multipart upload lên object store cần `complete` hoặc `abort`, không phải `Files.move`.
- Credential/IAM denied thường được SDK bọc thành service exception có HTTP 403 từ cloud API; đó là **backend IAM error**, không mặc định là HTTP 403 trả người dùng của app.
- S3 read stream phải close để trả connection về HTTP pool khi client SDK yêu cầu.
- Socket timeout và partial response có retry/chunking semantics khác local filesystem.
- Delete object/abort multipart có thể eventual và cần idempotency.
- Object versioning có thể khiến “delete” chỉ tạo delete marker, dữ liệu version vẫn tồn tại.
- Testcontainers/minio emulator hữu ích nhưng không chứng minh mọi cloud IAM/policy behavior.
- Production error logs không nên in access keys, presigned URLs hoặc private object names.

Để test cloud adapter, tách interface như StorageOps, mock SDK error types cho unit tests, rồi integration ở sandbox tenant/container thật. Cần assert cleanup theo **object IDs/upload IDs** thuộc test, không gọi “delete all bucket” trên tài nguyên dùng chung.

## 35. Filesystem test và HTTP test không chứng minh cùng một thứ

Hai assertions:

```java
assertThrows(AccessDeniedException.class,
        () -> store.save(input));
```

và

```java
mvc.perform(multipart("/api/documents").file(file))
   .andExpect(status().isInternalServerError());
```

là ở hai boundary khác nhau. Test thứ nhất dùng fake IO để chứng minh **reaction của store** trước AccessDeniedException; test thứ hai dùng mocked store để chứng minh **exception mapping của MVC**. Chỉ khi chạy full integration với NIO thật và fault injection đúng bean wiring mới kiểm được toàn chuỗi trong một lần. Không báo cáo “đã kiểm storage permission trên Windows/Linux production” chỉ vì hai test này xanh.

Tương tự, `@SpringBootTest + @AutoConfigureMockMvc` chạy nhiều beans thật nhưng **không mở TCP socket**. Muốn test multipart size limit của servlet container, upload có chunked transfer/truncated body, real client disconnect, proxy timeout, cần chạy `RANDOM_PORT` hoặc môi trường sát production.

## 36. Những anti-pattern thường gặp

| Anti-pattern | Lý do sai | Cách thay |
|---|---|---|
| `Files.copy(input, finalPath)` rồi bỏ input | Stream có thể không được đóng, final partial | Try-with-resources + staging |
| Catch IOException rồi trả 201 | False success, dữ liệu dở | Propagate/map error và cleanup |
| Dùng `MultipartFile.getOriginalFilename()` làm Path | Path traversal/collision | Server-generated ID |
| `new File("/tmp/shared.txt")` trong tests | Cross-test collision | JUnit @TempDir |
| Chỉ test happy path | Không phát hiện leak/partial data | Failure matrix |
| Dùng chmod để gây AccessDenied trên mọi CI | Không portable/root bypass | Fault-injection IO adapter |
| Map mọi AccessDeniedException thành HTTP 403 | Lẫn OS với app authZ | Rõ error source/contract |
| `catch(IOException ignored)` khi delete temp | Orphan bị giấu | Suppressed + metrics/janitor |
| Move final trước khi close input/output | Close failure sau publication | Close trước promote |
| Bỏ qua `OutputStream.close()` failure | Bytes có thể chưa flush/commit | Propagate failure |
| Đọc file GB bằng `readAllBytes()` | RAM exhaustion | Bounded streaming |
| `Files.list/walk` không close | Directory handle leak | Try-with-resources |
| `resolve(userPath).normalize()` là đủ an toàn | Symlink/TOCTOU còn tồn tại | Secure directory/ACL strategy |
| `@WebMvcTest` pass → parser TCP đã test | Mock multipart không parse network | Real HTTP test |
| Delete toàn storage root sau mỗi test | Phá files của tests khác | @TempDir/test-owned prefix |
| Gọi delete ngay mọi `.part` | Có thể xóa upload đang chạy | Lease/age/ownership janitor |
| Retry upload không idempotency | Duplicate documents | Idempotency key/registry |
| Test assert exact OS error message | Provider/platform-specific | Assert type + business contract |
| Dùng production credentials/path trong test | Rủi ro dữ liệu thật | Test-only temp/IAM account |

## 37. Troubleshooting theo triệu chứng

| Triệu chứng | Điều tra |
|---|---|
| Sau lỗi copy vẫn còn `.part` | Cleanup chưa chạy, delete lỗi, stage path không tracked |
| HTTP 201 nhưng file không đọc được | Return trước close/promote; move/file provider lỗi |
| Test đỏ ngẫu nhiên trên Windows | Input/Files.list stream chưa đóng; antivirus lock |
| File upload vượt limit vẫn được chấp nhận | Chỉ set multipart parser limit, store không bound (hoặc ngược lại) |
| API trả 403 khi volume không ghi được | Mapping AccessDeniedException sai tầng |
| Response lỗi lộ `/srv/private` | Serialize exception message/raw stack |
| Dữ liệu “abc” thành “ab” sau lỗi | Partial copy được publish |
| Mockito permission test xanh nhưng prod fail | Unit reaction != real OS ACL/IAM config |
| Mỗi lần retry có thêm file UUID | Không có idempotency key |
| Upload 5MB pass MockMvc nhưng real app fail 413 | MockMultipart không chạy parser/proxy thật |
| File bị mất sau cleanup race | Janitor xóa stage active |
| `NoSuchFileException` thay `AccessDeniedException` | FS/provider/permission semantics khác |
| JUnit @TempDir không xóa được | Open handle, Files.walk stream, process đang giữ lock |
| Close exception che copy exception | Cleanup/finally không preserve suppressed |
| `Files.move` thành công rồi sau crash file mất | Chưa có fsync/durability contract |
| Symlink dưới root đọc ngoài root | Directory untrusted, nofollow/secure directory thiếu |
| Account A đọc document B | Chưa có Spring Security object-level auth |
| Spring context reuse trỏ temp dir đã xóa | @TempDir lifecycle không khớp cached context |

### 37.1. Quy trình debug

1. **Bắt đầu tại symptom:** HTTP status sai, file partial, stream leak, hay OS permission denied?
2. Xác định **lớp đang lỗi:** multipart parser, MVC, storage logic, filesystem, cloud SDK.
3. Xác định ai sở hữu InputStream/OutputStream và thời điểm close.
4. Ghi nhận primary exception và suppressed exceptions, không log secrets.
5. Kiểm stages/finals bằng `@TempDir` hoặc test-owned prefix.
6. Dùng fake IO adapter phát chính xác exception muốn test.
7. Nếu lỗi chỉ xảy ra trên Windows/container, chạy provider-specific test phù hợp.
8. Xem cleanup có cố xóa resource của worker khác không.
9. Xem retry/idempotency/lock khi request có thể hoàn tất rồi client timeout.
10. Đánh giá lại error contract public, logs và vận hành janitor.

## 38. Bài tập thực hành

### A. Lỗi stream đọc ở byte thứ hai

Một InputStream trả một byte rồi ném IOException. Nếu service mở staging và copy vào finalPath trực tiếp, điều gì xảy ra? Viết unit test dùng stream giả; assert input closed và staging không còn.

**Đáp án:** Có thể để lại partial file với một byte nếu không có cleanup. Dùng staging + try-with-resources + finally cleanup, không promote khi fail.

### B. Quyền thư mục

Một server chạy trong Docker container không có quyền ghi mounted volume. Spring `AccessDeniedException` được ném khi tạo temp. Nên trả HTTP 403 cho user đăng nhập hay 500/503 theo contract storage?

**Đáp án:** Đây thường là lỗi service infrastructure/OS, không tự biểu thị user thiếu quyền ứng dụng. Mẫu trả 500 error code neutral, logs vận hành ghi chẩn đoán an toàn.

### C. Move lỗi

Copy đủ bytes và close hai streams thành công nhưng move staging→final ném IOException. Test gì?

**Đáp án:** Không trả 201, không có final ID công bố, staging được cố xóa, error được giữ; test có thể inject move failure bằng Mockito.

### D. Cleanup cũng lỗi

Một upload lỗi write và file tạm không xóa được. Nếu code `finally { Files.delete(temp); }`, điều gì có thể bị che?

**Đáp án:** IOException delete có thể che lỗi write. Lưu primary và `addSuppressed(cleanup)` hoặc tổ chức AutoCloseable resources đúng.

### E. Close input lỗi

Server đã move final rồi InputStream.close ném IOException. Caller retry, tạo duplicate. Sửa thứ tự?

**Đáp án:** Close source/output trước promote; với distributed retries vẫn cần idempotency key.

### F. Close output lỗi

Copy xong nhưng OutputStream.close ném IOException do flush/storage error. Có được trả 201?

**Đáp án:** Không theo contract demo; phải coi close failure là thất bại, cleanup staging và ghi lỗi.

### G. Kiểm permission trên Windows

Test dùng `Files.setPosixFilePermissions`. Chạy Windows báo UnsupportedOperationException. Nên làm gì?

**Đáp án:** Unit test AccessDenied qua mocked IO adapter; OS-specific POSIX/Windows ACL tests dùng assumptions trên runner phù hợp.

### H. Resource leak từ Files.list

Một test gọi `Files.list(root).count()` mà không đóng stream. Tại sao có thể gây test teardown fail trên Windows?

**Đáp án:** Directory stream giữ handle đến khi close; dùng try-with-resources cho Stream<Path>.

### I. File name nguy hiểm

Client gửi `../../application.yml` trong multipart filename. Nếu server dùng raw filename, rủi ro gì và kiểm thế nào?

**Đáp án:** Path traversal/overwrite; tạo UUID server-side, validate ID và app-owned root, thêm negative test cho traversal, kiểm không có file ngoài root.

### J. 413 từ đâu?

MockMvc upload 2MB nhưng Spring servlet parser max-file-size đặt 1MB; test vẫn đi vào controller. Vì sao?

**Đáp án:** Mock multipart request không chạy parser network thật. Kiểm storage bound ở unit/full-context MockMvc, kiểm parser limit bằng real HTTP server test.

### K. Trả byte[] file 2GB

Service gọi `Files.readAllBytes` với file 2GB rồi trả `ResponseEntity<byte[]>`. Rủi ro?

**Đáp án:** Heap pressure/OOM. Dùng streaming/bounded reads và test client disconnect/resource closure; mẫu chỉ hỗ trợ ≤1MiB.

### L. S3 permission

Ứng dụng thiếu quyền `s3:PutObject`; SDK trả cloud 403. Có nên chuyển nó thành Spring Security 403 cho end user?

**Đáp án:** Không mặc định. Đó là IAM error của service/role. Public error contract và vận hành remediation khác user authorization.

### M. Crash giữa copy

Process bị kill trước `finally`, còn `.part`. Ai dọn và làm sao không xóa upload đang chạy?

**Đáp án:** Janitor có ownership/lease/age threshold/monitoring, không xóa ngay toàn bộ stages.

### N. Filesystem move “atomic”

Bạn gọi `Files.move(stage, final)` rồi nghĩ readers không thấy partial state trên mọi filesystem. Điều này được bảo đảm không?

**Đáp án:** Không. Muốn atomic rename, yêu cầu `ATOMIC_MOVE` khi provider hỗ trợ; vẫn cần durability/idempotency/recovery contract riêng.

### O. Kiểm no side effect trên denied HTTP

Alice không được đọc tài liệu Bob nhưng controller gọi storage.readBytes trước khi kiểm quyền rồi trả 403. Test chỉ assert 403 có đủ không?

**Đáp án:** Không. Assert zero storage calls và không lộ bytes; authorization phải trước IO.

### P. InputStream ownership

Một library method nhận InputStream nhưng tài liệu nói caller giữ quyền sở hữu. Method có được luôn close không?

**Đáp án:** Không. Close thuộc contract ownership; method demo khác vì đã tuyên bố nhận ownership. Cần test caller có thể tiếp tục dùng stream nếu API mượn stream.

## 39. Checklist cuối bài

- [ ] Tôi biết phân biệt IOException, AccessDeniedException, NoSuchFileException, FileSystemException.
- [ ] Tôi không nhầm OS permission denied với HTTP authentication/authorization denied.
- [ ] Contract method ghi rõ ai sở hữu InputStream và ai close.
- [ ] OutputStream/InputStream được close khi thành công và mọi nhánh lỗi.
- [ ] Output/input close xảy ra **trước khi publish** final object.
- [ ] Try-with-resources được dùng cho streams/readers/writers và Files.list/walk.
- [ ] Tôi biết suppressed exceptions và không để cleanup error che lỗi chính.
- [ ] Có giới hạn bytes khi đọc/ghi từ input không tin cậy.
- [ ] File staging được dùng thay vì ghi trực tiếp final name.
- [ ] Lỗi copy/write/close/move đều không trả success.
- [ ] Cleanup cố xóa staging theo đúng resource ownership.
- [ ] Cleanup failure có log/metric và được preserve trong error.
- [ ] Không xóa staging/final của request hoặc test khác.
- [ ] Generated final name không lấy từ originalFilename.
- [ ] ID/path được validate; root là app-owned directory.
- [ ] Symlink/TOCTOU/ACL được đánh giá khi root có thể bị actor khác sửa.
- [ ] Test dùng @TempDir thay vì đường dẫn cố định toàn máy.
- [ ] Permission failure được mock/fault-inject trên CI cross-platform.
- [ ] OS-specific permission tests có assumptions, không chạy không kiểm soát.
- [ ] Test assert stream closed và file staging không còn.
- [ ] Test không assert exact OS-localized exception messages.
- [ ] MockMvc errors trả status và code an toàn, không lộ internal path.
- [ ] MockMultipartFile không bị hiểu nhầm là real multipart parser.
- [ ] Có full-context integration với NIO thật trong temp directory.
- [ ] HTTP 401/403 và file ownership được kiểm riêng nếu app có nhiều users.
- [ ] Các file lớn không bị đọc toàn bộ vào RAM vô hạn.
- [ ] Download streaming có policy cho client disconnect/response committed.
- [ ] Move atomicity và fsync durability không được giả định từ ordinary Files.move.
- [ ] Có xử lý retry/idempotency khi client timeout sau publish.
- [ ] Crash cleanup, janitor và staging retention có thiết kế rõ.
- [ ] Logs không rò credentials, private paths hoặc dữ liệu nhạy cảm.
- [ ] Resource pools/remote streams được đóng đúng theo SDK contract.
- [ ] Kết luận QA phân biệt code review, simulated IO failures và actual OS/HTTP runs.

**Kết luận:** Kiểm thử tích hợp với file/stream không kết thúc ở “đọc/ghi thành công”. Một thiết kế đáng tin cần kiểm **nguyên nhân lỗi, trạng thái tài nguyên sau lỗi và lời hứa với client**. Sử dụng `try-with-resources`, staging file, close-before-publish, bounded copy và cleanup có preserved suppressed exceptions; dùng `@TempDir` cho filesystem thật và fake IO adapter để inject permission/read/write/move errors trên mọi OS. `@WebMvcTest` bảo vệ error mapping, còn full-context và real HTTP/volume tests kiểm đúng những ranh giới quan trọng hơn. Không đánh đồng test mô phỏng AccessDeniedException với việc deployment thực đã được cấp quyền, và không coi Java finally là bảo đảm cleanup sau crash.

### Tài liệu tham khảo chính thức

- Java SE 17 — Files, copy/move/createTempFile/newInputStream/newOutputStream: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Java SE 17 — `AccessDeniedException` / `FileSystemException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/AccessDeniedException.html
- Java SE 17 — Throwable suppressed exceptions: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html
- Java Tutorials — try-with-resources và suppressed exceptions: https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html
- Spring Framework 6.2 — MockMvc request builders, multipart simulation: https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework.html
- Spring Boot 3.5 — Testing Spring Boot applications, @WebMvcTest và MockMvc: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Getting Started — Uploading Files, MultipartFile và MockMvc tests: https://spring.io/guides/gs/uploading-files/
- Spring Framework 6.2 — `MultipartFile` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/multipart/MultipartFile.html
- JUnit Jupiter — @TempDir temporary directories: https://junit.org/junit5/docs/current/user-guide/#writing-tests-built-in-extensions-TempDirectory
- OWASP — File Upload Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html
