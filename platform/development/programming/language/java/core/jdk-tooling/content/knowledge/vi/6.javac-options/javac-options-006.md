# Tùy chọn -Werror của javac

`-Werror` là tùy chọn của trình biên dịch Java `javac`. Khi được bật, nếu quá trình biên dịch phát sinh cảnh báo (warning), `javac` sẽ kết thúc với trạng thái thất bại. Nhờ đó, nhóm phát triển có thể ngăn mã nguồn mới đưa thêm cảnh báo vào dự án và làm cho quy trình build trong CI kiểm tra chất lượng nghiêm ngặt hơn.

Bản thân `-Werror` không tạo ra các cảnh báo. Nó thay đổi cách trình biên dịch xử lý những cảnh báo đã được phát hiện. Để kiểm soát loại cảnh báo cần phát hiện, thường kết hợp `-Werror` với các tùy chọn `-Xlint`.

## 1. Phân biệt warning và error

Trong quá trình biên dịch, `javac` có thể phát hiện nhiều loại vấn đề:

- **Error:** lỗi khiến mã nguồn không thể được biên dịch thành công, chẳng hạn sai cú pháp hoặc tham chiếu đến một phương thức không tồn tại.
- **Warning:** vấn đề đáng chú ý nhưng không nhất thiết ngăn chương trình được biên dịch, chẳng hạn sử dụng kiểu raw, thao tác không an toàn với generic hoặc gọi API đã deprecated.
- **Note:** thông tin bổ sung của trình biên dịch; note không phải lúc nào cũng là một warning.

Khi không dùng `-Werror`, một số cảnh báo vẫn cho phép `javac` biên dịch thành công và tạo bytecode. Khi dùng `-Werror`, nếu có warning thì lần biên dịch được xem là thất bại và trả về mã thoát khác 0.

Điều này hữu ích trong tự động hóa: CI có thể đánh dấu build thất bại thay vì cho phép cảnh báo mới đi qua mà không được xử lý.

## 2. Cú pháp và cách kết hợp tùy chọn

Cú pháp cơ bản:

```bash
javac -Werror TenLop.java
```

Trong thực tế, nên kết hợp với `-Xlint` để bật những nhóm cảnh báo cần kiểm tra.

| Tùy chọn | Công dụng |
| --- | --- |
| `-Werror` | Kết thúc biên dịch với trạng thái thất bại nếu phát sinh warning |
| `-Xlint` | Bật các nhóm cảnh báo bổ sung được trình biên dịch hỗ trợ |
| `-Xlint:all` | Bật các nhóm cảnh báo được khuyến nghị |
| `-Xlint:unchecked` | Hiển thị chi tiết cảnh báo về thao tác unchecked |
| `-Xlint:deprecation` | Hiển thị chi tiết cảnh báo khi dùng API deprecated |
| `-Xlint:rawtypes` | Cảnh báo khi dùng kiểu generic dạng raw type |

Ví dụ:

```bash
javac -Xlint:all -Werror Main.java
```

Lệnh này yêu cầu trình biên dịch bật các nhóm cảnh báo được khuyến nghị và coi warning phát sinh là lỗi của lần build.

**Lưu ý:** `-Werror` không tự bật mọi nhóm cảnh báo. Nếu chỉ dùng `-Werror`, những cảnh báo mà compiler không phát hiện hoặc chưa được bật vẫn có thể không xuất hiện. Vì vậy, chính sách thường dùng là kết hợp với một tập `-Xlint` phù hợp.

## 3. Ví dụ tạo warning bằng raw type

Một nguyên nhân phổ biến của warning là sử dụng collection không khai báo kiểu phần tử (raw type).

Tạo tệp **`WarningDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WarningDemo {
    public static void main(String[] args) {
        List values = new ArrayList();
        values.add("Java");

        System.out.println(values.get(0));
    }
}
```

Trong ví dụ, `List` và `ArrayList` được dùng mà không chỉ định kiểu phần tử. Lệnh `add()` vì vậy có thể phát sinh cảnh báo unchecked.

Biên dịch với cảnh báo unchecked:

```bash
javac -Xlint:unchecked WarningDemo.java
```

Trình biên dịch sẽ hiển thị warning chỉ ra thao tác unchecked tại dòng thêm phần tử. Câu chữ và số dòng cụ thể phụ thuộc phiên bản JDK.

Chạy chương trình:

```bash
java WarningDemo
```

Kết quả:

```text
Java
```

Chương trình vẫn có thể chạy đúng trong ví dụ nhỏ này, nhưng raw type làm mất kiểm tra kiểu tại thời điểm biên dịch và có thể dẫn đến lỗi ép kiểu khi chương trình lớn hơn.

## 4. Dùng -Werror để chặn warning

Thử biên dịch cùng tệp với:

```bash
javac -Xlint:unchecked -Werror WarningDemo.java
```

Vì mã nguồn phát sinh warning unchecked, `javac` kết thúc lần biên dịch với trạng thái thất bại. Thông báo thường cho biết có warning và tùy chọn `-Werror` đã được chỉ định. Nội dung chẩn đoán chính xác có thể thay đổi theo JDK.

Điểm quan trọng:

- Không có warning: `-Werror` không tự làm lần biên dịch thất bại.
- Có warning được phát hiện: lần biên dịch thất bại.
- Warning vẫn cần được sửa tại nguyên nhân hoặc được xử lý bằng một ngoại lệ có chủ đích.
- `-Werror` áp dụng cho warning do compiler phát hiện trong lần biên dịch; nó không tự động biến mọi thông báo của mọi công cụ build thành lỗi.

## 5. Sửa warning bằng generic type

Cách sửa tốt nhất trong ví dụ trên là khai báo kiểu phần tử cho collection.

Thay nội dung `WarningDemo.java` bằng:

```java
import java.util.ArrayList;
import java.util.List;

public class WarningDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>();
        values.add("Java");

        System.out.println(values.get(0));
    }
}
```

Biên dịch với chính sách nghiêm ngặt hơn:

```bash
javac -Xlint:all -Werror WarningDemo.java
java WarningDemo
```

Kết quả:

```text
Java
```

Với khai báo `List<String>`, trình biên dịch biết collection chỉ nhận các chuỗi và có thể kiểm tra kiểu an toàn hơn. Ví dụ không còn raw type và unchecked warning tương ứng.

Đây là cách xử lý nên ưu tiên: sửa nguyên nhân của warning thay vì tắt cảnh báo để build vượt qua.

## 6. Dùng -Werror với các nhóm cảnh báo khác

Ngoài unchecked warning, `javac` có thể phát hiện nhiều vấn đề khác.

### API deprecated

Một API được đánh dấu `@Deprecated` vẫn có thể còn tồn tại và biên dịch được, nhưng nhà phát triển được thông báo rằng API đó không còn được khuyến nghị sử dụng.

Dùng:

```bash
javac -Xlint:deprecation -Werror Main.java
```

Nếu mã nguồn sử dụng API deprecated và compiler phát ra warning tương ứng, lần biên dịch sẽ thất bại. Hãy đọc tài liệu API để tìm phương thức hoặc lớp thay thế.

### Raw types

Dùng:

```bash
javac -Xlint:rawtypes -Werror Main.java
```

Cảnh báo này giúp phát hiện các khai báo như `List`, `Map` hoặc `Set` không có tham số kiểu. Với mã Java sử dụng generic, nên khai báo rõ kiểu phần tử hoặc kiểu key/value.

### Bật nhiều nhóm cảnh báo

Dùng:

```bash
javac -Xlint:all -Werror Main.java
```

Cách này phù hợp với dự án muốn áp dụng chính sách kiểm tra cảnh báo rộng. Trước khi bật trên toàn bộ mã nguồn cũ, nên chạy thử để biết số lượng và loại warning hiện có.

## 7. Khi nào nên sử dụng -Werror?

`-Werror` đặc biệt hữu ích trong các tình huống:

- **CI/CD:** ngăn build thành công khi mã nguồn phát sinh warning mà chính sách dự án không cho phép.
- **Dự án mới:** thiết lập tiêu chuẩn chất lượng từ đầu để warning được xử lý ngay khi xuất hiện.
- **Thư viện dùng chung:** phát hiện sớm API deprecated, generic không an toàn và các vấn đề có thể ảnh hưởng người dùng thư viện.
- **Code review:** giúp nhóm tập trung xử lý warning trước khi hợp nhất thay đổi.
- **Nâng cấp JDK:** phát hiện warning mới do compiler phiên bản mới bổ sung hoặc thay đổi cách chẩn đoán.

Với mã nguồn cũ có nhiều warning, bật `-Werror` ngay có thể khiến build thất bại hàng loạt. Nên thống kê warning hiện có, sửa theo nhóm, rồi bật chính sách nghiêm ngặt khi baseline đã sạch.

## 8. Kết hợp với Maven

Nếu dự án dùng Maven Compiler Plugin, có thể truyền các tùy chọn compiler qua cấu hình plugin trong `pom.xml`.

Ví dụ:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <compilerArgs>
                    <arg>-Xlint:all</arg>
                    <arg>-Werror</arg>
                </compilerArgs>
            </configuration>
        </plugin>
    </plugins>
</build>
```

Khi chạy:

```bash
mvn clean compile
```

Maven chuyển các tùy chọn này đến compiler khi biên dịch mã nguồn. Nếu compiler phát sinh warning, bước compile thất bại và Maven báo build failure.

Phiên bản plugin trong ví dụ là một phiên bản cụ thể để minh họa cấu hình; dự án cần dùng phiên bản được tổ chức phê duyệt và tương thích với Maven/JDK hiện tại.

## 9. Kết hợp với Gradle

Với Gradle dùng Groovy DSL, có thể cấu hình các tác vụ biên dịch Java:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-Xlint:all', '-Werror']
}
```

Với Kotlin DSL trong `build.gradle.kts`:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.addAll(listOf("-Xlint:all", "-Werror"))
}
```

Các ví dụ này giả định dự án đã áp dụng Java plugin để có kiểu tác vụ `JavaCompile`.

Khi chạy:

```bash
./gradlew clean compileJava
```

Trên Windows:

```powershell
.\gradlew.bat clean compileJava
```

Nếu compiler phát ra warning, tác vụ biên dịch Java sẽ thất bại. Với dự án nhiều module, hãy thống nhất cấu hình giữa các module để tránh module này nghiêm ngặt còn module khác bỏ qua warning.

## 10. Xử lý warning có chủ đích

Không phải warning nào cũng có thể loại bỏ ngay. Một số trường hợp có lý do kỹ thuật để chấp nhận, ví dụ tương tác với API cũ, thư viện bên ngoài hoặc đoạn mã tương thích ngược.

Nếu đã xác minh warning là chấp nhận được, có thể dùng `@SuppressWarnings` ở phạm vi nhỏ nhất có thể:

```java
@SuppressWarnings("unchecked")
private static void legacyBridge() {
    // Chỉ đặt ngoại lệ tại đoạn mã đã được kiểm tra an toàn.
}
```

Đây là ví dụ minh họa phạm vi annotation; trong mã thực tế, chỉ dùng annotation khi có thao tác cụ thể phát sinh đúng loại warning đó.

Nguyên tắc:

- Đọc và hiểu nguyên nhân warning trước khi suppress.
- Chỉ suppress đúng nhóm cảnh báo cần thiết.
- Đặt annotation ở phương thức, biến hoặc đoạn mã có phạm vi hẹp nhất phù hợp.
- Giải thích lý do trong comment hoặc tài liệu khi quyết định không thể tránh warning.
- Không dùng `@SuppressWarnings("all")` để che giấu hàng loạt cảnh báo.

`-Werror` vẫn có giá trị khi dự án có ngoại lệ được xem xét kỹ: mọi warning còn lại tiếp tục bị chặn.

## 11. Những lưu ý khi đưa -Werror vào dự án

### Warning có thể thay đổi theo JDK

Phiên bản JDK mới có thể bổ sung cảnh báo, thay đổi mức độ chi tiết hoặc phát hiện thêm trường hợp mà compiler cũ chưa báo. Vì vậy, một dự án đang build thành công với `-Werror` có thể thất bại sau khi đổi JDK dù mã nguồn không thay đổi.

Khi nâng cấp JDK:

1. Chạy build với đúng JDK mới trong môi trường kiểm thử.
2. Thu thập và phân loại warning mới.
3. Xác định warning đến từ mã dự án, mã sinh tự động, annotation processor hay công cụ build.
4. Sửa mã nguồn hoặc cập nhật dependency/plugin phù hợp.
5. Chỉ điều chỉnh lint/suppress khi có lý do kỹ thuật rõ ràng.

### Mã sinh tự động và dependency

Mã nguồn được sinh tự động có thể phát ra warning mà nhóm phát triển không trực tiếp viết. Hãy xem xét cách cấu hình tác vụ hoặc compiler cho phần mã sinh ra, đồng thời tránh tắt cảnh báo cho toàn bộ mã nguồn chỉ vì một thư mục có vấn đề.

Các warning từ mã trong thư viện đã biên dịch thường khác với warning từ mã nguồn đang được biên dịch. `-Werror` không thay thế việc quản lý dependency và kiểm tra chất lượng thư viện bên ngoài.

### Không nhầm warning của javac với warning của runtime

`-Werror` là tùy chọn của compiler `javac`. Nó không phải tùy chọn chung để biến mọi log warning khi ứng dụng đang chạy thành lỗi. Logging framework, JVM runtime, Maven, Gradle và các plugin có chính sách warning riêng.

Nếu muốn build thất bại khi một công cụ khác phát warning, cần cấu hình chính sách riêng cho công cụ đó.

## 12. Quy trình áp dụng đề xuất

Một quy trình an toàn để triển khai `-Werror`:

1. Chạy `javac -Xlint:all` hoặc cấu hình tương đương trong build tool để thu thập warning hiện tại.
2. Phân loại warning theo nguyên nhân và mức độ ảnh hưởng.
3. Sửa lỗi trong mã nguồn: dùng generic, thay API deprecated, sửa resource handling hoặc các vấn đề compiler chỉ ra.
4. Với warning không thể tránh, đánh giá và suppress trong phạm vi hẹp, kèm lý do.
5. Bật `-Werror` trong module đã sạch warning.
6. Chạy toàn bộ build và test trong môi trường CI.
7. Duy trì chính sách này khi cập nhật JDK, compiler plugin hoặc dependency.

Với dự án cũ, có thể áp dụng dần theo module hoặc theo phần mã nguồn mới, sau đó mở rộng khi các warning tồn đọng đã được xử lý.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Build thất bại sau khi thêm `-Werror` | Compiler đã phát hiện ít nhất một warning | Đọc warning đầu tiên và sửa nguyên nhân |
| Dùng `-Werror` nhưng vẫn không thấy warning mong muốn | Nhóm lint tương ứng chưa được bật hoặc warning không thuộc phạm vi javac | Bật `-Xlint` phù hợp và kiểm tra công cụ phát cảnh báo |
| Nâng JDK làm build cũ thất bại | Compiler mới phát sinh thêm warning hoặc thay đổi chẩn đoán | Phân loại warning mới và cập nhật mã/cấu hình có chủ đích |
| Dùng `@SuppressWarnings` nhưng build vẫn thất bại | Annotation không áp dụng cho đúng loại warning hoặc phạm vi | Kiểm tra key warning, vị trí annotation và thông báo compiler |
| Tắt toàn bộ lint để build qua | Cảnh báo bị che đi, rủi ro không được phát hiện | Bật lại các nhóm cần thiết và sửa warning theo từng nhóm |
| Maven/Gradle vẫn báo warning | Cảnh báo có thể đến từ plugin hoặc tác vụ khác, không phải javac | Xác định chính xác công cụ phát cảnh báo và cấu hình chính sách tương ứng |

## 14. Ghi nhớ

- `-Werror` yêu cầu `javac` kết thúc thất bại khi phát sinh warning.
- `-Werror` không tự bật tất cả nhóm cảnh báo; kết hợp với `-Xlint` để xác định những gì cần kiểm tra.
- `-Xlint:all -Werror` là cấu hình nghiêm ngặt thường dùng cho mã nguồn Java.
- Sửa nguyên nhân warning là lựa chọn ưu tiên; chỉ dùng `@SuppressWarnings` khi có lý do rõ ràng và phạm vi hẹp.
- Warning mới có thể xuất hiện khi nâng JDK, vì vậy cần chạy lại build và test sau cập nhật.
- `-Werror` chỉ điều khiển warning của compiler; các công cụ khác cần chính sách riêng.

Áp dụng `-Werror` cùng với lint phù hợp giúp giữ mã nguồn Java sạch cảnh báo và làm cho CI phát hiện sớm những vấn đề mà nhóm phát triển cần xử lý.
