# Phân biệt phiên bản ngôn ngữ, API, bytecode và bản cập nhật JDK

Khi nói một dự án sử dụng Java 21, cụm từ này có thể đề cập đến nhiều lớp khác nhau: cú pháp và quy tắc của ngôn ngữ Java, các API mà chương trình được phép sử dụng, định dạng bytecode được tạo ra, hoặc bản cập nhật cụ thể của JDK đang dùng để biên dịch và chạy ứng dụng. Những lớp này có liên quan nhưng không đồng nhất.

Phân biệt chúng giúp trả lời chính xác các câu hỏi như: mã nguồn có dùng được cú pháp Java 21 không, chương trình có gọi được API chỉ xuất hiện từ Java 21 không, JVM có nạp được file `.class` không, và việc cập nhật từ JDK 21.0.1 lên một bản 21.0.x mới hơn có làm thay đổi mức tương thích hay không.

## 1. Bốn khái niệm cần phân biệt

| Khái niệm | Quyết định điều gì? | Ví dụ với Java 21 |
|---|---|---|
| Phiên bản ngôn ngữ (language version) | Cú pháp, quy tắc kiểu và ngữ nghĩa mã nguồn mà trình biên dịch chấp nhận | Pattern matching for `switch`, record patterns đã trở thành tính năng chính thức |
| Phiên bản API (API level) | Các package, class, interface, field và method mà mã nguồn có thể tham chiếu | `List.getFirst()` thuộc API Sequenced Collections được bổ sung trong Java 21 |
| Phiên bản bytecode (class-file version) | Định dạng file `.class` mà JVM cần hiểu để nạp và thực thi | Java 21 tạo class file có major version là `65` |
| Bản cập nhật JDK (JDK update) | Mức sửa lỗi, bảo mật và cập nhật triển khai của một feature release | Các bản `21.0.x` vẫn thuộc dòng Java 21 |

Có thể xem đây là bốn câu hỏi độc lập:

- **Ngôn ngữ:** Trình biên dịch có hiểu cách viết này không?
- **API:** Những kiểu và phương thức mà mã nguồn gọi có tồn tại trong phiên bản mục tiêu không?
- **Bytecode:** JVM đích có hỗ trợ định dạng file lớp được tạo ra không?
- **JDK update:** Bộ công cụ và runtime đã nhận các bản sửa lỗi, bảo mật cần thiết chưa?

## 2. Phiên bản ngôn ngữ Java

Phiên bản ngôn ngữ xác định tập cú pháp và quy tắc của mã nguồn. Một tính năng ngôn ngữ mới có thể yêu cầu trình biên dịch ở phiên bản tương ứng trở lên.

Ví dụ, pattern matching for `switch` là tính năng chính thức trong Java 21:

```java
class Main {
    static String describe(Object value) {
        return switch (value) {
            case String text -> "Chuỗi: " + text;
            case Integer number -> "Số nguyên: " + number;
            case null -> "Không có giá trị";
            default -> "Kiểu dữ liệu khác";
        };
    }
}
```

Trình biên dịch hỗ trợ Java 21 hiểu cú pháp mẫu kiểu trong các nhánh `case`. Nếu yêu cầu biên dịch theo ngôn ngữ Java 17, đoạn mã này không hợp lệ vì tính năng trên chưa thuộc ngôn ngữ Java 17.

Phiên bản ngôn ngữ không được quyết định chỉ bởi phiên bản runtime cài trên máy người dùng. Nó được kiểm soát ở bước biên dịch bằng compiler và cấu hình source level. Với `javac`, tùy chọn `--source` đặt mức ngôn ngữ cần biên dịch:

```bash
javac --source 21 Main.java
```

Trong dự án thực tế, nên cấu hình mức phát hành thống nhất bằng `--release` như phần sau, thay vì chỉ đặt source level riêng lẻ.

### Tính năng preview

Một số tính năng được phát hành dưới dạng preview để thu thập phản hồi trước khi trở thành chính thức. Tính năng preview phải được bật rõ ràng khi biên dịch và chạy; nó không có cùng cam kết ổn định với tính năng đã được chuẩn hóa.

Với Java 21, nếu chủ động thử một preview feature, cả compiler và JVM đều cần bật preview tương ứng, ví dụ bằng `--enable-preview`. Artifact preview gắn với feature release đã tạo ra nó và cần runtime đúng release cùng tùy chọn bật preview. Vì vậy, preview không nên được xem là nền tảng mặc định cho mã nguồn ứng dụng ổn định.

## 3. Phiên bản API Java

API là tập hợp các package, class, interface, constructor, field và method mà chương trình có thể sử dụng. Phiên bản API quyết định một lời gọi cụ thể có tồn tại trong nền tảng mục tiêu hay không.

Ví dụ, Java 21 bổ sung Sequenced Collections. Do đó, một chương trình có thể gọi `List.getFirst()` khi biên dịch theo API Java 21:

```java
import java.util.List;

class Main {
    public static void main(String[] args) {
        List<String> names = List.of("An", "Bình");
        System.out.println(names.getFirst());
    }
}
```

Mã nguồn trên dùng cú pháp Java đã có từ trước, nhưng method `getFirst()` chỉ có trong API bắt đầu từ Java 21. Nếu biên dịch với API mục tiêu Java 17, compiler sẽ không tìm thấy method này. Điều đó cho thấy mức ngôn ngữ và mức API là hai khía cạnh khác nhau: mã có thể dùng cú pháp cũ nhưng vẫn phụ thuộc API mới.

Cũng cần phân biệt API Java SE với API riêng của nhà cung cấp hoặc API nội bộ của JDK. Ứng dụng nên ưu tiên API công khai được tài liệu hóa và tránh phụ thuộc vào các package nội bộ như `sun.*`, vì chúng không có cam kết tương thích như API công khai.

### Vì sao cần kiểm soát API mục tiêu?

Giả sử dự án được biên dịch trên JDK mới hơn Java 21. Compiler có thể nhìn thấy các API mới hơn có trong JDK đang cài. Nếu chỉ đặt source level và target bytecode là 21, mã nguồn vẫn có nguy cơ gọi một method chỉ xuất hiện ở phiên bản Java cao hơn. File `.class` khi đó có thể mang định dạng Java 21 nhưng ứng dụng vẫn không chạy được trên Java 21 vì runtime thiếu method được gọi.

Đây là một lý do quan trọng để dùng `javac --release 21`: tùy chọn này kết hợp mức ngôn ngữ, mức bytecode và tập API công khai của phiên bản phát hành mục tiêu.

## 4. Phiên bản bytecode và class file

Sau khi biên dịch, mã nguồn Java được chuyển thành bytecode và lưu trong file `.class`. JVM đọc định dạng class file để xác minh, liên kết và thực thi lớp. Mỗi feature release của Java tương ứng với một mức class-file version.

Java 21 sử dụng **major version 65**. Đây là số phiên bản định dạng file lớp, không phải số phiên bản ngôn ngữ hay số bản cập nhật JDK.

| Nền tảng Java | Major version của class file |
|---|---:|
| Java 17 | 61 |
| Java 21 | 65 |

Nếu một class file được tạo bởi compiler mới hơn và có major version mà JVM cũ không hỗ trợ, JVM sẽ từ chối nạp lớp. Lỗi thường gặp là `UnsupportedClassVersionError`.

Thông thường, JVM mới có thể nạp class file được tạo cho phiên bản cũ hơn. Tuy nhiên, điều đó không bảo đảm toàn bộ ứng dụng chạy đúng: chương trình vẫn có thể phụ thuộc API, thư viện hoặc hành vi runtime không tương thích.

### Kiểm tra bytecode được tạo ra

Biên dịch một lớp theo Java 21:

```bash
javac --release 21 -d out Main.java
```

Sau đó xem thông tin class file:

```bash
javap -verbose -classpath out Main
```

Trong kết quả, tìm dòng tương tự:

```text
major version: 65
```

Lệnh `javap -verbose` giúp kiểm tra định dạng class file thực tế, thay vì suy đoán chỉ từ tên thư mục hoặc cấu hình của IDE.

### Bytecode đúng phiên bản chưa đủ để bảo đảm tương thích

Giả sử compiler Java 21 tạo class file có định dạng tương thích Java 17 nhưng mã trong đó gọi `List.getFirst()`, một method chỉ có từ API Java 21. Điều này có thể xảy ra nếu cấu hình chỉ dùng riêng `-source 17` và `-target 17`: compiler giới hạn cú pháp và bytecode nhưng vẫn nhìn thấy API của JDK 21. JVM 17 có thể nạp định dạng class file đó, nhưng khi liên kết lời gọi method, runtime Java 17 không có method này và có thể phát sinh `NoSuchMethodError`.

Nếu class file thực sự có major version 65, JVM 17 sẽ từ chối nạp lớp trước khi tới bước liên kết method và thường báo `UnsupportedClassVersionError`. Hai trường hợp này minh họa hai loại không tương thích khác nhau: định dạng bytecode và API runtime. Đây là lý do không nên dùng riêng `-source` và `-target` thay cho `--release` khi cần kiểm soát tương thích API.

## 5. Vai trò của `--release`

Tùy chọn `--release` của `javac` yêu cầu compiler biên dịch mã nguồn theo một phiên bản phát hành cụ thể. Với Java 21:

```bash
javac --release 21 -d out Main.java
java -cp out Main
```

Khi dùng `--release 21`, compiler kiểm soát đồng thời:

1. **Ngôn ngữ:** chỉ chấp nhận cú pháp và quy tắc của Java 21.
2. **Bytecode:** tạo class file tương thích với Java 21, major version 65.
3. **API:** giới hạn việc tham chiếu API công khai theo phiên bản Java 21.

Điểm cần nhớ là `--release` không tự chọn JDK cài đặt hoặc JDK dùng để chạy ứng dụng. Nó cấu hình mục tiêu biên dịch. Compiler đang sử dụng phải hỗ trợ release được yêu cầu; một JDK mới hơn có thể biên dịch cho Java 21 nếu compiler của nó còn hỗ trợ release đó.

Không nên trộn `--release` với `--source` hoặc `--target` trong cùng một lệnh. Hãy dùng một cấu hình mục tiêu rõ ràng để tránh tạo artifact có bytecode đúng nhưng lại phụ thuộc API sai phiên bản.

## 6. Bản cập nhật JDK 21

Số `21` trong JDK 21 xác định feature release. Sau khi feature release được phát hành, nhà cung cấp JDK tiếp tục phát hành các bản cập nhật thuộc cùng dòng, thường có dạng `21.0.x`. Một chuỗi phiên bản đầy đủ có thể còn chứa số build và thông tin phân phối.

Có thể đọc một chuỗi dạng `21.0.x+build` theo cách khái quát:

- `21`: feature release Java 21.
- `.0.x`: số cập nhật trong dòng phát hành đó.
- `+build`: thông tin build của bản phân phối.

Các bản cập nhật JDK cùng dòng chủ yếu cung cấp bản vá bảo mật, sửa lỗi, cập nhật dữ liệu nền tảng như múi giờ hoặc chứng thư, và cải tiến triển khai. Chúng không biến JDK 21 thành một feature release mới, không nâng mức ngôn ngữ lên Java 22 và không đổi major version bytecode chuẩn của Java 21.

Tuy nhiên, không nên cho rằng mọi bản cập nhật đều không thể ảnh hưởng đến hành vi ứng dụng. Một bản sửa lỗi hoặc thay đổi bảo mật có thể làm lộ ra giả định sai trong ứng dụng, thay đổi cách xử lý một trường hợp biên hoặc siết chặt hành vi vốn không được đặc tả. Vì vậy, sau khi cập nhật JDK vẫn cần chạy kiểm thử phù hợp với ứng dụng.

### Feature release, update và nhà cung cấp

| Thành phần | Ý nghĩa | Điều cần quan tâm |
|---|---|---|
| Feature release | Dòng phiên bản nền tảng, ví dụ Java 21 | Tính năng ngôn ngữ, API và mức bytecode |
| Update release | Bản cập nhật trong cùng dòng, ví dụ một bản `21.0.x` mới hơn | Bản vá bảo mật, sửa lỗi và mức cập nhật runtime/compiler |
| Nhà cung cấp JDK | Tổ chức xây dựng và phân phối JDK | Lịch cập nhật, thời hạn hỗ trợ, giấy phép, cách đóng gói và nền tảng hỗ trợ |

Nhãn LTS (Long-Term Support) mô tả chính sách hỗ trợ của nhà cung cấp hoặc nhà phân phối. Nó không phải một cú pháp ngôn ngữ, mức bytecode hay cam kết rằng mọi bản phân phối đều có cùng thời hạn hỗ trợ. Khi chọn JDK cho môi trường làm việc hoặc production, cần kiểm tra chính sách hỗ trợ và bản cập nhật bảo mật của đúng nhà cung cấp đang sử dụng.

Nên duy trì các môi trường build, kiểm thử và production trên bản cập nhật được nhà cung cấp hỗ trợ. Trong cùng dòng Java 21, việc nâng từ một bản `21.0.x` cũ lên bản cập nhật mới hơn thường không yêu cầu thay đổi mức `--release 21`, nhưng vẫn cần xác minh dependency và chạy kiểm thử hồi quy.

## 7. Cấu hình dự án để giữ tương thích Java 21

Một dự án cần xác định rõ JDK dùng cho build và mức phát hành mục tiêu. Hai cấu hình này có mục đích khác nhau:

- **Toolchain/JDK build** chọn bộ JDK thực hiện biên dịch, chạy test và các tác vụ phát triển.
- **Release target** quy định ngôn ngữ, bytecode và API mà artifact được phép phụ thuộc.

Ví dụ với Maven Compiler Plugin phiên bản hiện hành có hỗ trợ thuộc tính `maven.compiler.release`:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Ví dụ với Gradle Groovy DSL:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 21
}
```

Toolchain chọn JDK 21 cho tác vụ biên dịch; `options.release = 21` giới hạn đầu ra theo Java 21. Cấu hình thực tế cần phù hợp với phiên bản Maven/Gradle và plugin của dự án. Nếu tổ chức dùng JDK mới hơn để build nhưng vẫn triển khai Java 21, có thể chọn toolchain mới hơn và giữ release target là 21, miễn là compiler hỗ trợ release đó.

Ngoài cấu hình build, cần kiểm tra runtime triển khai. Một ứng dụng được biên dịch đúng theo Java 21 vẫn có thể gặp lỗi nếu dependency yêu cầu Java mới hơn hoặc môi trường chạy sử dụng JDK cũ hơn mức hỗ trợ.

## 8. Kiểm tra phiên bản trong môi trường thực tế

Các lệnh sau cho biết công cụ được phân giải từ môi trường dòng lệnh hiện tại:

```bash
java --version
javac --version
javap --version
```

Không nên mặc định rằng `java` và `javac` luôn đến từ cùng một JDK. IDE, build tool, terminal và CI có thể đang sử dụng các đường dẫn hoặc toolchain khác nhau. Khi kết quả không như mong đợi, hãy kiểm tra cấu hình JDK của từng môi trường.

Một số dấu hiệu thường gặp giúp xác định lớp có vấn đề:

| Triệu chứng | Khả năng cần kiểm tra |
|---|---|
| Compiler báo lỗi cú pháp hoặc không nhận diện pattern trong `switch` | Mức ngôn ngữ/source level hoặc phiên bản compiler |
| Compiler báo không tìm thấy method có trong Java 21 | API mục tiêu đang thấp hơn hoặc compiler không dùng API Java 21 |
| JVM báo `UnsupportedClassVersionError` | Bytecode được tạo bởi compiler mới hơn mức JVM hỗ trợ |
| Runtime báo `NoSuchMethodError` | API hoặc phiên bản dependency lúc chạy không khớp với lúc biên dịch |
| Runtime có lỗi đã được sửa trong bản JDK mới | Bản cập nhật JDK, nhà cung cấp và cấu hình runtime |

Các triệu chứng trên là manh mối ban đầu; cần đọc đầy đủ stack trace và xác định chính xác class, method hoặc tiến trình liên quan trước khi kết luận nguyên nhân.

## 9. Quy tắc áp dụng cho dự án Java 21

Khi dự án công bố yêu cầu chạy trên Java 21, nên xác định và ghi lại tối thiểu các thông tin sau:

- JDK vendor và bản cập nhật JDK được dùng trong build/CI.
- Mức ngôn ngữ mà mã nguồn sử dụng.
- API mục tiêu là Java SE 21.
- Bytecode mục tiêu là Java 21, major version 65.
- Phiên bản runtime và bản cập nhật JDK được triển khai.
- Các dependency và công cụ build có hỗ trợ Java 21 hay không.

Với ứng dụng cần tương thích Java 21, cấu hình `--release 21` hoặc tùy chọn tương đương của build tool là cách rõ ràng để khóa đồng thời ngôn ngữ, API và bytecode mục tiêu. Đồng thời, duy trì JDK update được hỗ trợ và kiểm thử trên runtime triển khai giúp phát hiện sớm sai khác giữa môi trường phát triển và production.

Điểm cốt lõi là: **ngôn ngữ quyết định cách viết mã, API quyết định những thành phần có thể gọi, bytecode quyết định JVM có đọc được file lớp, còn JDK update quyết định mức vá lỗi và bảo mật của bộ công cụ/runtime**. Chỉ xác nhận một trong bốn điều này là chưa đủ để khẳng định ứng dụng tương thích Java 21.
