# Tên automatic module từ Automatic-Module-Name

## 1. Bối cảnh và mục tiêu

Từ Java 9, Java Platform Module System (JPMS) cho phép ứng dụng tổ chức mã thành **named modules**. Trong giai đoạn chuyển thư viện cũ sang module path, nhiều JAR chưa có `module-info.class`. Khi đặt một JAR như vậy trên **module path**, Java có thể coi nó là **automatic module** để các module đã khai báo rõ ràng có thể sử dụng thư viện đó.

Điểm quan trọng của bài này là: tác giả thư viện có thể khai báo **tên module ổn định** bằng thuộc tính `Automatic-Module-Name` trong manifest của JAR. Người dùng thư viện sẽ dùng đúng tên đó trong câu lệnh `requires` của `module-info.java`.

Sau bài này, bạn có thể:
- Phân biệt tên module lấy từ manifest với tên tự suy ra từ tên file JAR.
- Khai báo `Automatic-Module-Name` khi đóng gói JAR.
- Dùng tên module đã khai báo trong `requires` và kiểm tra bằng công cụ `jar`.
- Nhận biết những lỗi thường gặp khi một thư viện được đưa lên module path.

## 2. Java xác định tên automatic module như thế nào?

Một JAR **không chứa module descriptor** `module-info.class` được xem là automatic module khi được đặt trên module path. Java xác định tên của nó theo thứ tự sau:

1. Nếu phần manifest chính (`META-INF/MANIFEST.MF`) có thuộc tính `Automatic-Module-Name` hợp lệ, dùng **giá trị thuộc tính đó**.
2. Nếu không có thuộc tính này, Java **suy ra tên từ tên file JAR**, loại phần phiên bản và chuẩn hóa các dấu phân cách theo quy tắc của JPMS.

Ví dụ, file `example-util-1.0.jar` có thể được suy ra thành `example.util`. Nếu manifest ghi `Automatic-Module-Name: com.example.util`, tên module là **`com.example.util`**, bất kể tên file JAR chứa phiên bản nào.

| Tình huống | Tên module được dùng |
| --- | --- |
| JAR có `module-info.class` | Tên trong câu lệnh `module ... { }` của module descriptor |
| JAR chưa có descriptor, manifest có `Automatic-Module-Name` | Giá trị `Automatic-Module-Name` |
| JAR chưa có descriptor và không có thuộc tính trên | Tên suy ra từ tên file JAR |

**Lưu ý:** Khi JAR đã có module descriptor thực sự, tên trong descriptor có hiệu lực; manifest không đổi tên một explicit module. Thuộc tính `Automatic-Module-Name` cũng không biến JAR thành explicit module.

## 3. Khai báo Automatic-Module-Name trong MANIFEST.MF

Giả sử thư viện có các lớp trong package `com.example.util`, được đóng gói thành `example-util-1.0.jar`. Ta muốn các ứng dụng luôn gọi thư viện bằng tên module `com.example.util`.

Nội dung manifest tối thiểu có thể là:

```text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.util

```

Thuộc tính phải nằm trong **main section** của file `META-INF/MANIFEST.MF`. Dòng trống cuối cùng kết thúc section. Khi dùng công cụ đóng gói JAR, nên để công cụ sinh và chuẩn hóa manifest thay vì chỉnh sửa tùy tiện file nằm trong JAR.

Tên module `com.example.util` là tên Java hợp lệ, dùng dấu chấm để phân cấp. Nên dùng quy ước tên đảo ngược miền giống tên package. Các tên chứa dấu gạch ngang, dấu cách, hoặc thành phần không phải định danh Java hợp lệ không phù hợp với tên module.

Tên này là **giao ước công khai của thư viện**: khi ứng dụng đã viết `requires com.example.util;`, đổi tên module sẽ làm mã ứng dụng phải sửa theo.

### Đóng gói thủ công với jar

Giả sử các file `.class` đã được biên dịch vào thư mục `build/util-classes`, còn nội dung manifest ở file `manifest.mf`:

```bash
jar --create --file example-util-1.0.jar --manifest manifest.mf -C build/util-classes .
```

JAR thành phẩm phải có manifest khai báo tên ở trên và chứa các lớp thư viện. Đặt JAR đó lên module path để Java nhận diện là automatic module.

### Cấu hình Maven

Với dự án đóng gói kiểu `jar`, có thể cấu hình `maven-jar-plugin` trong `pom.xml`:

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-jar-plugin</artifactId>
      <configuration>
        <archive>
          <manifestEntries>
            <Automatic-Module-Name>com.example.util</Automatic-Module-Name>
          </manifestEntries>
        </archive>
      </configuration>
    </plugin>
  </plugins>
</build>
```

Sau khi đóng gói, hãy kiểm tra **JAR cuối cùng được phát hành**. Nếu quy trình còn có bước tạo fat JAR, shading hoặc repackaging, cần bảo đảm manifest trong artifact cuối vẫn giữ đúng thuộc tính này.

### Cấu hình Gradle (Groovy DSL)

Trong `build.gradle`:

```groovy
tasks.withType(Jar).configureEach {
    manifest {
        attributes('Automatic-Module-Name': 'com.example.util')
    }
}
```

Nếu dự án có nhiều nhiệm vụ tạo JAR, kiểm tra manifest của đúng artifact mà người dùng tải về.

## 4. Sử dụng tên đó từ một explicit module

Giả sử thư viện có lớp:

```java
package com.example.util;

public final class Texts {
    private Texts() {}

    public static String trimToEmpty(String input) {
        return input == null ? "" : input.trim();
    }
}
```

Ứng dụng có module descriptor `src/app/module-info.java` như sau:

```java
module com.example.app {
    requires com.example.util;
}
```

Lớp chính của ứng dụng:

```java
package com.example.app;

import com.example.util.Texts;

public class Main {
    public static void main(String[] args) {
        System.out.println(Texts.trimToEmpty("  Xin chào JPMS  "));
    }
}
```

Ở đây `requires com.example.util;` tham chiếu **tên module trong manifest**, không phải tên Maven artifact, tên file JAR đầy đủ hoặc tên package của một lớp bất kỳ.

Ví dụ chạy trên môi trường có JDK 9 trở lên, khi `libs/` chứa `example-util-1.0.jar` và cấu trúc nguồn giống các đường dẫn trên:

```bash
javac --module-path libs -d build/app-classes src/app/module-info.java src/app/com/example/app/Main.java
java --module-path "libs:build/app-classes" --module com.example.app/com.example.app.Main
```

Đầu ra mong đợi:

```text
Xin chào JPMS
```

Trong lệnh `java`, dấu `:` phân tách nhiều mục của module path trên Linux/macOS; trên Windows, thay bằng dấu `;`. Tên automatic module chỉ tham gia cơ chế JPMS khi JAR ở **module path**. Khi cùng JAR nằm trên **classpath**, JVM xử lý nó theo cơ chế classpath truyền thống và không yêu cầu `requires` cho JAR đó.

## 5. Kiểm tra tên module thực tế

Không nên đoán tên module từ tên file hoặc tên thư viện được công bố. Dùng công cụ đi kèm JDK:

```bash
jar --describe-module --file example-util-1.0.jar
```

Với JAR chưa có `module-info.class` nhưng có manifest khai báo tên, công cụ sẽ mô tả một **automatic module** có tên `com.example.util`. Cách trình bày dòng kết quả có thể khác nhau giữa các phiên bản JDK; thông tin cần đối chiếu là **tên module** và **trạng thái automatic**.

Có thể xem manifest trực tiếp bằng công cụ giải nén JAR/ZIP để xác nhận mục `META-INF/MANIFEST.MF` có dòng:

```text
Automatic-Module-Name: com.example.util
```

Hãy xác minh trên **bản JAR thực sự được đưa vào module path**, đặc biệt khi dự án có các gói `sources`, `tests`, bản phân phối đã đổi tên hoặc quá trình đóng gói nhiều bước.

## 6. Automatic-Module-Name làm gì và không làm gì?

- **Ổn định tên để phụ thuộc:** thay vì viết `requires example.util;` theo tên file suy ra, ứng dụng có thể dùng `requires com.example.util;` nhất quán qua các phiên bản JAR.
- **Hỗ trợ di trú sang JPMS:** thư viện chưa có descriptor vẫn có thể được ứng dụng modular sử dụng trong giai đoạn chuyển đổi.
- **Không định nghĩa phụ thuộc của thư viện:** chỉ có tên trong manifest không tạo ra các câu `requires`, `exports` hay `opens` cho một explicit module.
- **Không tự modular hóa thư viện:** automatic module được JPMS đối xử linh hoạt, như đọc các module khác và xuất các package của nó, để tương thích với mã cũ. Cơ chế đó khác với việc khai báo quyền đọc, package xuất và package mở một cách có chủ đích trong `module-info.java`.
- **Không làm tên package và tên module thành một:** tên module thường gần với namespace thư viện nhưng là một danh tính riêng. Một module có thể chứa nhiều package.

Khi thư viện chuyển sang explicit module trong phiên bản sau, nên giữ lại chính xác tên `com.example.util` trong descriptor:

```java
module com.example.util {
    exports com.example.util;
}
```

Nhờ vậy, các ứng dụng vốn đã viết `requires com.example.util;` có thể giữ nguyên tên phụ thuộc. Tuy nhiên, việc chuyển sang explicit module vẫn có thể thay đổi mức độ truy cập vào các package và yêu cầu phụ thuộc, nên cần đánh giá tác động tương thích riêng.

## 7. Lỗi thường gặp và cách xác định nguyên nhân

### Lỗi: module not found: com.example.util

Nguyên nhân thường gặp:
- JAR chưa được đặt đúng trên module path của bước biên dịch/chạy.
- Manifest của artifact cuối không có `Automatic-Module-Name` như dự kiến.
- Tên trong `requires` khác tên thực tế của JAR (ví dụ dùng `example.util` trong khi manifest ghi `com.example.util`).

Cách xử lý: chạy `jar --describe-module --file ...` trên đúng JAR, rồi đối chiếu tên với `module-info.java` và tham số `--module-path`.

### Lỗi vì tên module trùng nhau

Hai JAR khác nhau cùng công bố `Automatic-Module-Name: com.example.util` không thể đại diện cho hai module riêng biệt với cùng tên trong một cấu hình module đã phân giải. Hãy bảo đảm mỗi thư viện có danh tính module duy nhất; rà soát các phiên bản JAR bị đưa vào cùng module path.

### Lỗi vì tên không hợp lệ

Giá trị như `example-util` chứa dấu gạch ngang nên không phải tên module Java hợp lệ. Hãy chọn tên như `com.example.util`, đóng gói lại, rồi kiểm tra kết quả bằng `jar --describe-module`.

### Lỗi do split package hoặc phụ thuộc chưa tương thích

Tạo tên module ổn định không giải quyết mọi xung đột module path. Nếu hai module cung cấp cùng một package hoặc thư viện cũ phụ thuộc vào mã chưa bố trí đúng classpath/module path, quá trình phân giải hay biên dịch vẫn có thể thất bại. Khi đó cần kiểm tra **cấu trúc package và sơ đồ phụ thuộc**, thay vì chỉ sửa tên manifest.

## 8. Khi nào nên khai báo thuộc tính này?

Tác giả của **thư viện JAR chưa có module descriptor** nên cân nhắc khai báo `Automatic-Module-Name` sớm, nhất là khi thư viện có người dùng đang chuyển ứng dụng sang JPMS. Một tên rõ ràng, ổn định giúp giảm rủi ro tên tự suy ra thay đổi khi đổi `artifactId`, cách đặt tên file hoặc quy trình phát hành.

Quy trình thực hành gợi ý:

1. Chọn tên module theo namespace ổn định, ví dụ `com.example.util`.
2. Đưa `Automatic-Module-Name` vào manifest của JAR phân phối.
3. Đóng gói bản phát hành và xác nhận tên bằng `jar --describe-module`.
4. Dùng đúng tên đó trong `requires` của ứng dụng modular.
5. Khi bổ sung `module-info.java` cho thư viện, tiếp tục dùng tên cũ và xem xét rõ các `requires`, `exports`, `opens` cần khai báo.

## 9. Tự luyện tập

**Bài 1.** Có file `client-tools-2.3.jar` chưa có descriptor, manifest ghi `Automatic-Module-Name: vn.example.client.tools`. Ứng dụng cần khai báo gì?

```java
module vn.example.app {
    requires vn.example.client.tools;
}
```

**Bài 2.** Một nhóm đổi tên file `client-tools-2.3.jar` thành `client-tools-2.4.jar` nhưng giữ manifest ở bài 1. Tên module có đổi không?

**Không.** Nếu JAR vẫn là automatic module, tên từ manifest vẫn là `vn.example.client.tools`.

**Bài 3.** Nếu xóa `Automatic-Module-Name` và giữ JAR trên module path, tên có còn được bảo đảm là `vn.example.client.tools` không?

**Không.** Java sẽ suy ra tên từ tên file JAR theo quy tắc của JPMS; tên này có thể khác tên đã dùng trong các câu `requires`.

## Ghi nhớ

`Automatic-Module-Name` là thuộc tính trong **manifest của JAR chưa modular hóa** giúp công bố **tên automatic module ổn định**. Java ưu tiên tên này so với tên suy ra từ file JAR khi thư viện được đặt trên **module path**. Dùng `jar --describe-module` để kiểm tra và tham chiếu đúng tên trong `requires`.