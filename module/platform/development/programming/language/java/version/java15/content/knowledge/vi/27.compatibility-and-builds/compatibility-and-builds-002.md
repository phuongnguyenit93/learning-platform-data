# Phân biệt khả năng compiler và runtime trong Java

## 1. Mục tiêu và ngữ cảnh

Khi xây dựng ứng dụng Java, câu “máy của tôi biên dịch được” **không đồng nghĩa** với “máy triển khai sẽ chạy được”. Hai câu hỏi cần trả lời riêng:

1. **Compiler có biên dịch được mã nguồn không?** `javac` hiểu cú pháp Java ở mức phiên bản nào, kiểm tra được những API nào, và tạo ra tệp `.class` thuộc phiên bản nào?
2. **Runtime có chạy được kết quả đó không?** Lệnh `java` khởi chạy JVM nào, JVM có đọc được định dạng `.class` không, và tại thời điểm chạy có đủ API, thư viện, module, cấu hình và tài nguyên cần thiết không?

Bài dùng **Java 15 làm mốc minh họa** vì thuộc module Java 15. Các nguyên tắc về cross-compilation, `--release`, tương thích bytecode, toolchain và kiểm thử runtime vẫn áp dụng cho các phiên bản Java hiện đại. Khi triển khai hệ thống mới, hãy chọn phiên bản JDK được nhà cung cấp hỗ trợ phù hợp với chính sách vận hành, thay vì mặc định lựa chọn Java 15.

## 2. Hai năng lực khác nhau trong cùng một quy trình

```text
Hello.java  ── javac ──>  Hello.class  ── java/JVM ──>  chương trình chạy
 mã nguồn         compile       bytecode         runtime
```

| Khía cạnh | Compiler (`javac`) | Runtime (`java` và JVM) |
|---|---|---|
| Đầu vào chính | Mã nguồn `.java`, dependency ở compile classpath/module path | `.class` hoặc JAR, dependency ở runtime classpath/module path |
| Kiểm tra quan trọng | Cú pháp, kiểu dữ liệu, lời gọi API nhìn thấy khi biên dịch, target của class file | Phiên bản class file, tải và liên kết lớp, hiện diện của API/dependency, điều kiện thực thi |
| Kết quả | Tạo bytecode `.class` hoặc báo lỗi biên dịch | Chạy ứng dụng hoặc phát sinh lỗi tải lớp, liên kết, cấu hình, logic |
| Phiên bản liên quan | JDK thực sự chạy compiler; `--release`; bộ thư viện dùng khi biên dịch | JVM thực sự chạy ứng dụng; class file và thư viện cần nạp |
| Điều **không** bảo đảm | Biên dịch thành công chưa chứng minh máy đích chạy thành công | JVM đủ mới để đọc bytecode chưa chứng minh mọi dependency và hành vi đều tương thích |

Một máy có thể có nhiều JDK. `javac -version` và `java -version` không nhất thiết trỏ đến cùng bản cài đặt. IDE, Maven, Gradle và CI có thể dùng compiler/JVM khác với terminal. Vì vậy, phải xác định **công cụ thực sự được gọi** chứ không suy đoán từ tên dự án.

## 3. Ba lớp tương thích cần kiểm tra

### 3.1. Mức ngôn ngữ (source level)

Compiler phải hiểu cú pháp được sử dụng. Chẳng hạn, **text block** là tính năng ngôn ngữ chính thức ở Java 15. Nếu yêu cầu biên dịch theo Java 11, compiler sẽ từ chối cú pháp text block ngay từ bước biên dịch, dù chính compiler đó đang chạy trên một JDK mới.

Năng lực hiểu cú pháp đến từ phiên bản compiler và tham số ngôn ngữ (ví dụ `--release 15` hoặc `--source 15`). Một compiler cũ không thể được “nâng” thành compiler mới chỉ bằng cách tăng target.

### 3.2. Định dạng bytecode (class-file level)

Tệp `.class` mang **major version**. JVM phải hỗ trợ major version đó mới có thể nạp lớp:

| Java phát hành | Major version thông thường |
|---|---:|
| Java 11 | 55 |
| **Java 15** | **59** |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

Ví dụ, JVM Java 11 không nạp được class file phiên bản 59 của Java 15 và thường báo `UnsupportedClassVersionError`. JVM mới thường đọc được class file từ các phiên bản cũ hơn, nhưng điều này mới chỉ thỏa **điều kiện định dạng bytecode**, chưa bảo đảm mọi API và thư viện sẽ hoạt động.

Để tự kiểm tra class file, dùng `javap -verbose -classpath out Hello` rồi tìm dòng `major version: 59` trong ví dụ bên dưới. Cần kiểm tra cả các class nằm trong các dependency, không chỉ class do dự án tự biên dịch.

### 3.3. API và môi trường runtime

Một lời gọi phương thức có thể hợp lệ đối với JDK dùng để biên dịch nhưng không tồn tại trên JVM đích. Khi liên kết lời gọi đó, runtime có thể báo `NoSuchMethodError`. Nếu thiếu class từ dependency, có thể gặp `NoClassDefFoundError` hoặc `ClassNotFoundException`, tùy cách nạp lớp và vị trí lỗi.

Ngay cả khi bytecode và API tương thích, vẫn cần kiểm tra phiên bản thư viện, module, tùy chọn JVM, cấu hình, kiến trúc/OS và thư viện native (nếu có). **Class-file major version chỉ là một phần của khả năng chạy.**

## 4. Cách biên dịch tương thích: ưu tiên `--release`

Với một JDK có hỗ trợ release 15, lệnh:

```bash
javac --release 15 -d out Hello.java
```

áp dụng đồng thời ba ràng buộc của Java 15:

1. **Quy tắc ngôn ngữ:** mã nguồn chỉ được dùng tính năng ngôn ngữ hợp lệ với release 15.
2. **Định dạng class file:** sinh bytecode mục tiêu Java 15 (major 59).
3. **API nền tảng:** khi biên dịch, chỉ nhìn thấy API Java SE/JDK được công bố cho release 15; lời gọi API mới hơn sẽ bị phát hiện.

`--release` giúp ngăn trường hợp “bytecode cũ nhưng vô tình gọi API JDK mới”. Đây là lựa chọn phù hợp cho bài toán dùng compiler mới để xây cho runtime cũ được xác định trước. Kiểm tra các release mà compiler đang cài đặt hỗ trợ bằng `javac --help`; một compiler không nhất thiết hỗ trợ mọi release lịch sử.

**Phân biệt ba tùy chọn:**

| Tùy chọn | Kiểm soát | Điểm cần nhớ |
|---|---|---|
| `--source 15` | Cú pháp và quy tắc ngôn ngữ Java 15 | Không tự giới hạn API của JDK dùng để compile |
| `--target 15` | Định dạng bytecode Java 15 | Không tự ngăn dùng API chỉ xuất hiện ở JDK mới hơn |
| `--release 15` | Source level **và** target bytecode **và** API nền tảng Java 15 | Nên dùng khi cam kết chạy trên Java 15 |

Không kết hợp `--release` với `--source` hoặc `--target` trong cùng lệnh. Đồng thời, `--release` **không** tự kiểm chứng API của mọi thư viện bên thứ ba, khả năng tương thích của dependency khi chạy hay mọi hành vi của ứng dụng. Vẫn phải kiểm thử trên runtime thực tế.

## 5. Ví dụ chạy được: compiler mới tạo chương trình chạy trên Java 15

Tạo tệp **`Hello.java`** với nội dung:

```java
public class Hello {
    public static void main(String[] args) {
        String message = """
                Xin chào Java %s
                """.formatted("15").strip();

        System.out.println(message);
    }
}
```

Đây là chương trình độc lập. Text block và `String.formatted(Object...)` đều có trong Java 15; `strip()` đã có từ Java 11. Text block có dấu xuống dòng cuối; `strip()` xóa phần khoảng trắng đầu/cuối, nên kết quả in ra chỉ có một dòng.

Trong thư mục chứa `Hello.java`, dùng JDK 15 hoặc JDK mới hơn **có hỗ trợ `--release 15`**:

```bash
mkdir out
javac --release 15 -d out Hello.java
java -cp out Hello
```

Stdout của lệnh cuối:

```text
Xin chào Java 15
```

Kiểm tra bytecode:

```bash
javap -verbose -classpath out Hello
```

Trong kết quả có dòng:

```text
major version: 59
```

Nếu dùng **Java 15 runtime** để chạy class này, chương trình hoạt động như trên. Nếu dùng **Java 11 runtime**, lớp không thể nạp vì major 59 mới hơn mức JVM đó hỗ trợ (55), nên xuất hiện `UnsupportedClassVersionError`. Lỗi này xảy ra **trước khi** chương trình thực thi `main`.

Nếu thay lệnh compile bằng `javac --release 11 -d out Hello.java`, source của ví dụ bị từ chối tại **compile time** do dùng tính năng/các API sau Java 11. Đó là thất bại của năng lực compiler theo release yêu cầu, không phải lỗi runtime.

## 6. Phản ví dụ quan trọng: bytecode cũ nhưng API quá mới

Tạo tệp riêng **`ApiMismatch.java`**:

```java
public class ApiMismatch {
    public static void main(String[] args) {
        System.out.println("Xin chào %s".formatted("Java"));
    }
}
```

`String.formatted(...)` xuất hiện từ Java 15. Giả sử ta dùng **compiler JDK 17** và chạy:

```bash
mkdir out
javac -source 11 -target 11 -d out ApiMismatch.java
```

Compiler có thể biên dịch thành công (có thể kèm cảnh báo), vì **`-source 11 -target 11` không tự thay API của JDK 17 bằng API Java 11**. Class tạo ra có major 55, tức định dạng mà JVM Java 11 có thể nạp. Tuy nhiên, khi chạy class trên **Java 11**, lời gọi `String.formatted` không tồn tại trong API runtime và có thể phát sinh:

```text
java.lang.NoSuchMethodError
```

Thông báo lỗi đầy đủ tùy phiên bản và JVM; dòng trên chỉ nêu **loại lỗi**, không phải toàn bộ stderr cố định.

Cách kiểm soát đúng khi muốn chạy trên Java 11:

```bash
javac --release 11 -d out ApiMismatch.java
```

Lần này compiler từ chối lời gọi `formatted` ngay khi biên dịch. Sửa chương trình để dùng API hợp lệ của Java 11, hoặc thay đổi yêu cầu runtime đích một cách có chủ đích. **Không “sửa” lỗi bằng cách hạ `--target` đơn lẻ.**

Trường hợp này cho thấy cần tách hai câu hỏi: **JVM đọc được class file không?** và **JVM có đủ API mà bytecode gọi tới không?**

## 7. Ma trận nhanh: compile và run có thành công không?

Các tình huống sau giả định JDK/compiler hỗ trợ release được chỉ định, mã nguồn hợp lệ và dependency tương thích trừ khi ghi khác:

| Tình huống | Compile | Chạy trên JVM đích | Vì sao? |
|---|---|---|---|
| JDK 17, `--release 15` → Java 15 | Có | Có, với chương trình `Hello` bên trên | Source, bytecode và API nền tảng khớp Java 15 |
| JDK 17, không đặt target → Java 15 | Có thể có | Không đối với class mặc định major 61 | JVM Java 15 không đọc class file của Java 17 |
| JDK 17, `--release 11` + text block → Java 11 | Không | Chưa đến bước chạy | Cú pháp text block vượt Java 11 |
| JDK 17, `-source 11 -target 11` + `String.formatted` → Java 11 | Có thể có | Không khi gọi API đó | Bytecode major 55 nhưng runtime thiếu phương thức |
| JDK 11, `--release 15` → Java 15 | Không | Chưa đến bước chạy | Compiler cũ không hỗ trợ release tương lai |
| JDK 21, `--release 15` nhưng dependency chỉ chạy Java 17+ → Java 15 | Mã dự án có thể compile | Không bảo đảm | Dependency có thể mang class file hoặc API vượt Java 15 |

“Compile thành công” ở hàng cuối không phải chứng nhận mọi dependency sẽ hoạt động trên máy đích. Đặc biệt, classpath dùng khi compile và khi run có thể chứa phiên bản thư viện khác nhau.

## 8. Áp dụng vào build bằng Maven hoặc Gradle

### Maven: khai báo release thay cho chỉ khai báo source/target

Với dự án Maven dùng Maven Compiler Plugin hỗ trợ thuộc tính này, đặt trong `pom.xml`:

```xml
<properties>
    <maven.compiler.release>15</maven.compiler.release>
</properties>
```

Thuộc tính chỉ định mục tiêu biên dịch. Phiên bản JDK mà Maven/Compiler Plugin **thực sự dùng** phải hỗ trợ release 15. Nếu cần chọn chính xác JDK để compile, dùng cơ chế **Maven Toolchains** hoặc cấu hình build tương đương. `mvn -version` cho biết JVM chạy Maven, nhưng không tự chứng minh đó là JDK của compiler khi đã cấu hình toolchain khác.

### Gradle: phân biệt compiler toolchain với target release

Ví dụ **`build.gradle`** (Groovy DSL), có Java 17 toolchain để compile nhưng tạo sản phẩm nhắm Java 15:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 15
}
```

Ở đây:

- `toolchain.languageVersion = 17` chọn **JDK dùng để compile** (và thường dùng cho các tác vụ Java theo toolchain).
- `options.release = 15` quy định **ngôn ngữ, bytecode và API nền tảng mục tiêu** của các JavaCompile task.
- Gradle chạy và test bằng JVM nào là **một kiểm tra riêng**. Nếu yêu cầu chạy trên Java 15, hãy cấu hình tác vụ test hoặc pipeline để thực thi bằng Java 15 tương ứng; chạy test trên Java 17 không thay thế được bước đó.

Để phát hành production, nên áp dụng cùng nguyên tắc cho **một phiên bản runtime đang được hỗ trợ** theo chính sách sản phẩm; giá trị 15 trong hai cấu hình chỉ nhằm minh họa bài học Java 15.

## 9. Preview features và giới hạn riêng của chúng

Với các tính năng ngôn ngữ đang ở trạng thái **preview** trong một JDK hiện đại, compiler và JVM thường đều phải bật `--enable-preview`. Preview được gắn chặt với **đúng phiên bản Java phát hành**, khác với cam kết tương thích của mã Java ổn định.

Ví dụ tổng quát, với JDK phiên bản `N` và một source thực sự dùng preview của chính `N`:

```bash
javac --enable-preview --release N Example.java
java --enable-preview Example
```

`N` ở đây là ký hiệu cho **số release đang dùng**, phải thay bằng số thực khi chạy; đây là cú pháp minh họa, không phải hai lệnh copy để chạy nguyên văn. Không dùng `--enable-preview` như cách vượt qua hạn chế chạy bytecode hoặc API mới trên JVM cũ. Class có preview marker yêu cầu JVM tương ứng và cờ phù hợp, đồng thời không thể mặc định chuyển sang JVM của release khác.

Đối với ứng dụng cần phân phối rộng rãi, kiểm tra rõ trạng thái **standard hay preview** của tính năng trên phiên bản đích. Bài này ưu tiên text block và `String.formatted` đã là tính năng/API ổn định ở Java 15.

## 10. Quy trình xác minh tương thích khi build và triển khai

1. **Chốt runtime đích.** Ghi rõ vendor, major release, bản vá và môi trường triển khai (máy chủ, container hoặc CI). Chọn phiên bản còn được hỗ trợ cho hệ thống mới.
2. **Chốt compiler thực tế.** Kiểm tra `javac -version`, `java -version`; với Maven/Gradle xem thêm toolchain, cấu hình IDE và CI. Đừng giả định chúng trùng nhau.
3. **Biên dịch bằng `--release <phiên-bản-đích>`** khi compiler hỗ trợ, để kiểm soát cú pháp, bytecode và API nền tảng cùng lúc.
4. **Kiểm tra dependency.** Xác nhận class file và yêu cầu Java tối thiểu của từng thư viện quan trọng; kiểm tra runtime classpath/module path và phiên bản dependency thực sự đóng gói.
5. **Kiểm tra artifact.** Dùng `javap -verbose` trên class đại diện (và class nghi ngờ trong dependency) để xác nhận major version; kiểm tra manifest, entry point và cấu hình đóng gói nếu dùng JAR.
6. **Chạy test trên JVM đích.** Thực thi unit/integration/smoke tests bằng JVM tương thích với môi trường triển khai; thử luồng thực tế chạm đến các API/dependency quan trọng. Test chỉ trên JDK compiler chưa đủ.
7. **Kiểm chứng bản triển khai.** Ghi nhận `java -version` ngay trong môi trường chạy, xác nhận biến môi trường, JVM flags, quyền truy cập và thư viện native khi có.

Lệnh kiểm tra cơ bản:

```bash
javac -version
java -version
javac --help
```

`javac --help` cho biết các phiên bản `--release` compiler hiện tại chấp nhận. Khi dùng container, chạy `java -version` **bên trong image/runtime thực tế**, không chỉ trên máy người phát triển.

## 11. Nhận diện và xử lý lỗi theo đúng giai đoạn

| Dấu hiệu | Giai đoạn | Hướng kiểm tra |
|---|---|---|
| Compiler không hiểu cú pháp hoặc `invalid source release` | Compile | Compiler có đủ mới không, `--release` đang chọn gì? |
| `cannot find symbol` với API mới | Compile | API có được giới thiệu sau release đích không? Có dùng `--release` đúng không? |
| `UnsupportedClassVersionError` | Khi JVM nạp lớp | So major của class với JVM đích; rà cả dependency |
| `NoSuchMethodError`, `NoSuchFieldError` | Liên kết/thực thi | API runtime có tồn tại không, có lệch phiên bản thư viện không? |
| `NoClassDefFoundError` hoặc `ClassNotFoundException` | Nạp/tìm lớp | Dependency, classpath/module path, đóng gói và class loader |
| Build/test thành công ở CI nhưng deploy thất bại | Khác biệt môi trường | Kiểm tra JVM thật của CI và production, dependency runtime, flags, OS/native |

**Hai lỗi hay gặp:**

- Đặt `sourceCompatibility`/`targetCompatibility` hoặc `-source`/`-target` rồi kết luận hệ thống đã an toàn với JDK cũ. Cặp cấu hình đó chưa khóa API nền tảng: cần `--release` và test trên JVM đích.
- Thấy Java mới chạy được bytecode cũ rồi coi việc nâng runtime luôn an toàn. Vẫn phải đánh giá thay đổi API/hành vi, dependency, cấu hình, quyền truy cập module và kiểm thử tích hợp.

## 12. Tự kiểm tra hiểu bài

**Tình huống A:** Laptop dùng JDK 21 biên dịch một class Java 15 bằng `--release 15`; server cài JVM 15. Có chắc chạy không?

**Trả lời:** Compiler đã kiểm soát mức ngôn ngữ, bytecode và API nền tảng của mã được biên dịch. Nhưng chưa thể chắc chắn nếu còn dependency, cấu hình hay môi trường chạy khác; cần test trên JVM 15 và artifact triển khai thực tế.

**Tình huống B:** `javap` báo class major 55; server JVM 11 cũng hỗ trợ major 55. Vì sao vẫn xuất hiện `NoSuchMethodError`?

**Trả lời:** Định dạng bytecode tương thích nhưng class có thể gọi API chỉ xuất hiện trong JDK mới hơn hoặc phiên bản dependency khác với lúc compile. Đối chiếu runtime API và cấu hình `--release`.

**Tình huống C:** Nâng `--target` lên 17 trên compiler JDK 11 để bật cú pháp Java 17 có được không?

**Trả lời:** Không. Compiler JDK 11 không hiểu cú pháp mới của Java 17; target bytecode không nâng được năng lực parser/compiler.

**Tình huống D:** Java 17 compiler build `--release 15` rồi test trên Java 17. Đã xác nhận chạy ở Java 15 chưa?

**Trả lời:** Chưa. Hãy chạy test/smoke test trên Java 15, kiểm cả dependency và môi trường. Cờ `--release` không thay JVM đang chạy test.

## 13. Ghi nhớ

**Compiler quyết định mã có biên dịch được và sẽ tạo bytecode/API mục tiêu nào; runtime quyết định artifact ấy có thực sự nạp, liên kết và chạy được trong môi trường đích hay không.** Ba mức cần giữ riêng là **cú pháp nguồn**, **phiên bản class file**, và **API/dependency lúc chạy**. Với cross-compilation, ưu tiên `--release`, sau đó xác minh bằng JVM thật của môi trường triển khai.

### Tài liệu chính thức để tra cứu

- [Oracle: `javac` — `--release`, `--source` và `--target`](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [Java Virtual Machine Specification: Class File Format](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-4.html)
- [JDK 15 API: `String.formatted`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/String.html)
- [Gradle: JVM toolchains và `options.release`](https://docs.gradle.org/current/userguide/toolchains.html)
- [Maven Compiler Plugin: cấu hình compiler release](https://maven.apache.org/plugins/maven-compiler-plugin-4.x/examples/set-compiler-release.html)
