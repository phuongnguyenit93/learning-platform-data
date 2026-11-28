# Đọc tài liệu, Javadoc và ghi chú phát hành đúng phiên bản

Spring Shell cung cấp nền tảng để xây dựng ứng dụng dòng lệnh theo mô hình Spring. Ứng dụng có thể khai báo command, nhận argument và option, kiểm tra dữ liệu đầu vào, hiển thị trợ giúp, gợi ý lệnh khi nhấn Tab, rồi chạy ở chế độ tương tác hoặc không tương tác. Khi phát triển các chức năng này, tài liệu tham khảo phải khớp với phiên bản Spring Shell thực sự có trong ứng dụng.

Một ví dụ trên mạng có thể dùng annotation, package hoặc cách cấu hình đã thay đổi ở phiên bản mới. Nếu chép ví dụ đó vào dự án cũ, IDE có thể không tìm thấy class hoặc chương trình có thể chạy với hành vi khác dự kiến. Quy trình đáng tin cậy là xác định phiên bản đã được resolve, mở tài liệu và Javadoc tương ứng, đọc các thay đổi phát hành kể từ phiên bản đó, rồi kiểm chứng ví dụ bằng chính dependency của dự án.

## 1. Vì sao phải kiểm tra phiên bản trước khi đọc tài liệu?

Số phiên bản Spring Shell thường có dạng `MAJOR.MINOR.PATCH`, chẳng hạn `4.0.4`:

- **MAJOR** thể hiện một thế hệ API; nâng phiên bản lớn có thể kèm thay đổi không tương thích.
- **MINOR** bổ sung tính năng và có thể thay đổi cách dùng trong phạm vi tương thích mà dự án cam kết.
- **PATCH** chủ yếu sửa lỗi và cập nhật dependency; vẫn cần đọc ghi chú phát hành vì một bản vá có thể sửa hành vi mà ứng dụng đang phụ thuộc.

Phiên bản Spring Shell còn phải tương thích với Spring Boot, Spring Framework và JDK của ứng dụng. Ví dụ, Spring Shell 4 dựa trên Spring Framework 7 và yêu cầu Spring Boot 4 trở lên khi tích hợp với Spring Boot. Một dự án đang chạy Spring Boot 3 không thể chỉ đổi riêng dependency Spring Shell lên 4 rồi mặc định mọi thứ sẽ tương thích.

Các thế hệ cũng có thể thay đổi cấu trúc API. Trong Spring Shell 4, các package lõi nằm dưới `org.springframework.shell.core.*`; mô hình annotation sử dụng `@Command`, `@Argument` và `@Option`. Các annotation cũ như `@ShellComponent`, `@ShellMethod` và `@ShellOption`, vốn đã bị deprecated ở thế hệ 3, đã bị loại bỏ ở thế hệ 4. Vì vậy, tài liệu đúng chủ đề nhưng sai phiên bản vẫn có thể dẫn đến code không biên dịch.

## 2. Xác định phiên bản thực tế của dự án

Đừng chỉ nhìn vào số phiên bản được ghi trong một file cấu hình. Dependency có thể được quản lý bởi BOM, plugin hoặc dependency bắc cầu. Hãy kiểm tra cây dependency sau khi hệ thống build đã resolve phiên bản.

### Với Maven

Chạy lệnh sau tại thư mục chứa `pom.xml`:

```bash
# Linux hoặc macOS
./mvnw dependency:tree -Dincludes=org.springframework.shell

# Windows
mvnw.cmd dependency:tree -Dincludes=org.springframework.shell
```

Kết quả cho biết những artifact thuộc nhóm `org.springframework.shell` và phiên bản mà Maven thực sự chọn. Hãy chú ý cả dependency trực tiếp lẫn dependency bắc cầu. Nếu dự án khai báo một property như sau, property đó giúp tập trung quản lý phiên bản nhưng chưa thay thế việc kiểm tra cây dependency:

```xml
<properties>
    <spring-shell.version>4.0.4</spring-shell.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.shell</groupId>
        <artifactId>spring-shell-starter</artifactId>
        <version>${spring-shell.version}</version>
    </dependency>
</dependencies>
```

Nếu dự án dùng BOM hoặc khai báo version ở một parent POM, hãy lần theo dependency management để biết nơi quyết định phiên bản. Không kết luận rằng dependency đang chạy phiên bản nào chỉ từ một property chưa được kiểm tra.

### Với Gradle

Để xem lý do một phiên bản được chọn trong `runtimeClasspath`, dùng `dependencyInsight`:

```bash
# Linux hoặc macOS
./gradlew dependencyInsight \
    --dependency spring-shell-core \
    --configuration runtimeClasspath

# Windows
gradlew.bat dependencyInsight --dependency spring-shell-core --configuration runtimeClasspath
```

Nếu dự án chỉ khai báo starter, Gradle vẫn có thể hiển thị `spring-shell-core` như một dependency bắc cầu. Có thể thay tên module trong `--dependency` bằng artifact Spring Shell mà dự án đang dùng.

### Ghi lại bộ phiên bản liên quan

Trước khi tra cứu, ghi lại tối thiểu:

| Thành phần | Thông tin cần xác định | Vì sao cần biết |
|---|---|---|
| Spring Shell | Phiên bản đã resolve, ví dụ `4.0.4` | Chọn đúng reference documentation, Javadoc và release notes |
| Spring Boot | Phiên bản đang dùng hoặc không dùng Boot | Kiểm tra khả năng tương thích và auto-configuration |
| Spring Framework | Phiên bản được quản lý trong dependency graph | Xác định baseline framework phù hợp |
| JDK | Phiên bản compiler và runtime | Kiểm tra yêu cầu ngôn ngữ, API JDK và công cụ build |

Khi có nhiều module hoặc nhiều cấu hình build, hãy kiểm tra đúng module và classpath liên quan đến ứng dụng đang chạy. Phiên bản trên `testRuntimeClasspath` có thể khác cấu hình runtime của một module khác.

## 3. Chọn đúng Reference Documentation

Reference Documentation giải thích khái niệm, cách cấu hình và ví dụ sử dụng. Đây thường là điểm bắt đầu tốt khi cần hiểu một tính năng như đăng ký command, phân tích argument, validation, completion, xử lý output hoặc chế độ chạy.

Trang tài liệu chính thức: [Spring Shell Reference Documentation](https://docs.spring.io/spring-shell/reference/).

Khi mở trang, hãy kiểm tra phiên bản hiển thị trong phần tiêu đề và bộ chọn phiên bản. Đừng chỉ dựa vào tên trang hoặc kết quả tìm kiếm. Cổng tài liệu có thể hiển thị nhánh ổn định mới nhất, trong khi dự án của bạn vẫn dùng một nhánh cũ hơn. Với các nhánh đã phát hành, Spring Shell cung cấp đường dẫn tài liệu theo dòng phiên bản, ví dụ [tài liệu nhánh 3.3](https://docs.spring.io/spring-shell/reference/3.3/). Hãy chọn nhánh tương ứng với dependency của dự án và kiểm tra số phiên bản cụ thể được ghi trên trang.

Một số điểm cần xác minh khi đọc một trang hướng dẫn:

1. Phiên bản ghi trong trang có khớp với phiên bản dự án đang dùng không?
2. Ví dụ dùng đúng mô hình khai báo command của phiên bản đó không: annotation hay API lập trình?
3. Các property cấu hình có còn tồn tại và có cùng ý nghĩa không?
4. Ví dụ có giả định dùng Spring Boot, JLine hoặc một starter cụ thể không?
5. Trang có ghi rõ tính năng đang thử nghiệm, deprecated hoặc chỉ có từ một phiên bản nhất định không?

Không dùng tài liệu `SNAPSHOT`, milestone (`M`) hoặc release candidate (`RC`) làm căn cứ mặc định cho ứng dụng production. Những tài liệu này mô tả mã nguồn đang phát triển hoặc bản tiền phát hành; API và hành vi vẫn có thể thay đổi trước khi phát hành ổn định.

## 4. Dùng Javadoc để xác minh API

Reference Documentation cho biết cách sử dụng tính năng ở mức khái niệm. Javadoc giúp xác minh chính xác class, package, constructor, method, tham số, kiểu trả về và annotation attribute mà code có thể gọi.

Có thể mở Javadoc từ các trang chính thức sau:

- [Spring Shell 4.0.4 API](https://docs.spring.io/spring-shell/reference/api/): API của dòng 4.0.4 tại thời điểm biên soạn.
- [Spring Shell 3.3.4 API](https://docs.spring.io/spring-shell/docs/3.3.4/api/): Javadoc được đóng phiên bản cho dòng 3.3.4.

Khi dùng Javadoc, hãy tra cứu theo tên đầy đủ của class hoặc package đang xuất hiện trong source code. Chẳng hạn, package annotation của Spring Shell 4 nằm dưới `org.springframework.shell.core.command.annotation`, trong khi Javadoc Spring Shell 3.3.4 tổ chức API dưới các package `org.springframework.shell.*`. Khác biệt package là dấu hiệu rõ ràng cho thấy một đoạn code có thể thuộc thế hệ API khác.

Quy trình tra cứu một API:

1. Tìm package hoặc tên class từ import trong source code, hoặc từ lỗi biên dịch.
2. Mở Javadoc đúng phiên bản và xác nhận class đó có tồn tại trong package tương ứng.
3. Kiểm tra chữ ký method, kiểu tham số, kiểu trả về và các overload. Không suy ra chữ ký chỉ từ một đoạn code ví dụ.
4. Đọc mô tả annotation attribute, giá trị mặc định và điều kiện áp dụng.
5. Kiểm tra nhãn `Since`, `Deprecated` và liên kết tới phần thay thế nếu có.
6. Nếu API phụ thuộc module, kiểm tra dự án đã có đúng artifact chứa module đó chưa.

Ví dụ, một command đơn giản theo mô hình annotation của Spring Shell 4 có thể được khai báo như sau:

```java
import org.springframework.shell.core.command.annotation.Argument;
import org.springframework.shell.core.command.annotation.Command;
import org.springframework.stereotype.Component;

@Component
class GreetingCommands {

    @Command(name = "hello", description = "Chào một người dùng")
    String hello(
            @Argument(index = 0, description = "Tên người dùng") String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Các import và annotation trong ví dụ thuộc API Spring Shell 4. Khi dự án dùng Spring Shell 3, hãy mở Javadoc và Reference Documentation của nhánh 3 để chọn API tương ứng; không đổi import theo ví dụ này một cách máy móc. Sau khi đối chiếu, chạy build của dự án để compiler xác nhận class và chữ ký thực sự có trong dependency.

## 5. Đọc Release Notes và Migration Guide

Javadoc cho biết API tồn tại như thế nào; release notes giải thích điều gì đã thay đổi giữa các bản phát hành. Hai nguồn này bổ sung cho nhau. Một method vẫn có thể tồn tại nhưng hành vi, dependency mặc định hoặc cách cấu hình liên quan đã thay đổi.

Nguồn phát hành chính thức là [Spring Shell Releases trên GitHub](https://github.com/spring-projects/spring-shell/releases). Với một dự án đang dùng `3.3.4` và dự định nâng lên `4.0.4`, hãy đọc các bản phát hành trong khoảng phiên bản đó, sau đó đọc [hướng dẫn chuyển từ Spring Shell 3 sang 4](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide).

Khi đọc release notes, tập trung vào các nhóm thông tin sau:

- **New features:** tính năng mới và phiên bản đầu tiên hỗ trợ tính năng đó.
- **Enhancements:** thay đổi hoặc cải thiện cách một tính năng hiện có hoạt động.
- **Bug fixes:** lỗi đã được sửa; kiểm tra xem ứng dụng có đang dựa vào hành vi lỗi cũ hay không.
- **Deprecations và breaking changes:** API bị đánh dấu deprecated, bị xóa hoặc cần thay thế.
- **Dependency updates:** thay đổi phiên bản Spring Boot, Spring Framework, JLine hoặc thư viện liên quan.
- **Full Changelog:** danh sách commit hoặc thay đổi giữa hai tag khi phần mô tả ngắn chưa đủ chi tiết.

Ví dụ, release `4.0.4` được công bố ngày 19/11/2026. Ghi chú phát hành nêu tính năng thêm global prefix cho command, mở rộng command `script` để nhận tham chiếu classpath và các sửa lỗi liên quan đến parser, trợ giúp và xử lý command. Nếu ứng dụng đang dùng `4.0.3`, những thông tin này giúp xác định thay đổi nào có liên quan đến cách người dùng gọi command hoặc chạy script.

Với thay đổi lớn, hãy đọc Migration Guide trước khi sửa code. Hướng dẫn Spring Shell 4 nêu rõ baseline Spring Framework 7 và Spring Boot 4+, thay đổi cấu trúc module, chuyển package API và loại bỏ các annotation legacy như `@ShellComponent`, `@ShellMethod`, `@ShellOption`. Những thay đổi này ảnh hưởng đồng thời đến dependency, import và cách khai báo command; chỉ đọc trang hướng dẫn một tính năng riêng lẻ sẽ không cho thấy đầy đủ tác động nâng cấp.

Đừng chỉ đọc ghi chú của bản đích. Nếu nâng qua nhiều bản, hãy đọc thay đổi từ phiên bản đang dùng đến phiên bản dự định cài đặt. Điều này giúp phát hiện một property bị đổi tên ở bản trung gian hoặc một API đã deprecated trước khi bị xóa ở bản mới.

## 6. Một quy trình tra cứu có thể lặp lại

Khi gặp một vấn đề trong ứng dụng Spring Shell, có thể dùng trình tự sau:

```text
Source code và build file
          |
          v
Xác định dependency đã resolve
          |
          v
Kiểm tra Spring Boot / Framework / JDK
          |
          v
Mở Reference Documentation đúng nhánh
          |
          v
Đối chiếu package và chữ ký trong Javadoc
          |
          v
Đọc Release Notes / Migration Guide liên quan
          |
          v
Thử ví dụ bằng dependency của dự án
          |
          v
Ghi lại phiên bản, nguồn và kết luận
```

Ví dụ: dự án hiện resolve Spring Shell `3.3.4`, nhưng một bài hướng dẫn trên mạng dùng `org.springframework.shell.core.command.annotation.Command`. Trước hết, kiểm tra dependency tree để xác nhận dự án thực sự dùng 3.3.4. Tiếp theo, mở tài liệu và Javadoc 3.3.4; package `org.springframework.shell.core.*` thuộc API thế hệ 4 nên không thể lấy nguyên import đó cho dự án hiện tại. Nếu mục tiêu là nâng lên 4.0.4, kiểm tra Spring Boot và Spring Framework có đáp ứng baseline mới không, đọc Migration Guide, cập nhật dependency và sửa code theo API mới. Cuối cùng, build và chạy lại command để kiểm chứng.

Sau khi tra cứu, lưu một ghi chú ngắn có cấu trúc:

```text
Spring Shell đã resolve: 3.3.4
Spring Boot / Framework / JDK: <các phiên bản của dự án>
Reference Documentation: <URL và nhánh phiên bản>
Javadoc: <URL và package/class đã kiểm tra>
Release notes đã đọc: <các tag hoặc khoảng phiên bản>
Kết luận: <API hoặc cấu hình phù hợp với dự án>
Kiểm chứng: <lệnh build/test và kết quả>
```

Ghi rõ URL và phiên bản giúp thành viên khác kiểm tra lại kết luận, nhất là khi một trang tài liệu mặc định được cập nhật sang bản phát hành mới hơn.

## 7. Kiểm chứng ví dụ trước khi áp dụng

Một đoạn code có vẻ hợp lý trong tài liệu vẫn cần được kiểm tra trên classpath thực tế. Sau khi chọn đúng tài liệu và Javadoc:

1. Kiểm tra import và artifact chứa API.
2. Chạy compile để phát hiện class hoặc method không tồn tại.
3. Chạy test liên quan đến command, argument, option và validation.
4. Chạy ứng dụng ở chế độ mà người dùng sẽ sử dụng. Spring Shell có thể có khác biệt giữa interactive và non-interactive; đừng chỉ kiểm tra bằng cách gọi một method trực tiếp.
5. Kiểm tra help, completion, output và exit code nếu thay đổi có ảnh hưởng đến các hành vi đó.

Với Maven, bước compile cơ bản có thể chạy bằng:

```bash
# Linux hoặc macOS
./mvnw -DskipTests compile

# Windows
mvnw.cmd -DskipTests compile
```

Lệnh này chỉ xác nhận code biên dịch được; nó không thay thế test hành vi command hoặc kiểm thử tích hợp. Nếu ví dụ cần một starter hoặc module bổ sung, hãy thêm đúng dependency theo hướng dẫn của phiên bản đang dùng rồi kiểm tra lại dependency tree.

## 8. Bài tập thực hành

Giả sử một ứng dụng CLI đang dùng Spring Shell `3.3.4`. Bạn tìm được một ví dụ trên Internet dùng `@Command`, `@Argument` và import từ `org.springframework.shell.core.command.annotation`, đồng thời muốn đánh giá khả năng nâng lên `4.0.4`.

Hãy thực hiện các yêu cầu sau:

1. Dùng Maven hoặc Gradle xác định phiên bản Spring Shell đã resolve và ghi lại phiên bản Spring Boot, Spring Framework, JDK.
2. Mở Reference Documentation và Javadoc của Spring Shell `3.3.4`. Xác định package annotation mà phiên bản đó cung cấp.
3. Mở Javadoc `4.0.4` và so sánh package của `Command`, `Argument`, `Option`.
4. Đọc release notes và Migration Guide từ v3 lên v4. Liệt kê ít nhất ba thay đổi có thể ảnh hưởng đến dependency hoặc source code.
5. Đề xuất một lộ trình nâng cấp. Nêu rõ điều kiện tương thích cần đáp ứng trước khi thay đổi dependency.
6. Nếu tạo một nhánh thử nghiệm, cập nhật ví dụ command và chạy compile/test. Ghi lại lỗi hoặc kết quả xác minh.

**Kết quả cần có:** một bảng đối chiếu phiên bản, đường dẫn tài liệu/Javadoc đã dùng, danh sách thay đổi phát hành liên quan và kết quả kiểm chứng code. Không chỉ ghi “đã đọc tài liệu”; cần chỉ ra thông tin nào trong tài liệu đã quyết định cách triển khai.

## 9. Checklist trước khi tin vào một ví dụ

- [ ] Đã xác định phiên bản Spring Shell thực sự được resolve.
- [ ] Đã kiểm tra phiên bản Spring Boot, Spring Framework và JDK liên quan.
- [ ] Reference Documentation đang mở đúng nhánh và hiển thị đúng phiên bản.
- [ ] Javadoc xác nhận package, class, method và annotation attribute.
- [ ] Đã kiểm tra `Since`, `Deprecated` và các API thay thế.
- [ ] Đã đọc release notes từ phiên bản hiện tại đến phiên bản cần dùng.
- [ ] Đã đọc Migration Guide nếu có thay đổi major hoặc breaking change.
- [ ] Ví dụ đã được compile và kiểm thử trên dependency của dự án.

## Tài liệu tham khảo

- [Spring Shell Reference Documentation](https://docs.spring.io/spring-shell/reference/)
- [Spring Shell 3.3 Reference Documentation](https://docs.spring.io/spring-shell/reference/3.3/)
- [Spring Shell 4.0.4 Javadoc](https://docs.spring.io/spring-shell/reference/api/)
- [Spring Shell 3.3.4 Javadoc](https://docs.spring.io/spring-shell/docs/3.3.4/api/)
- [Spring Shell Releases](https://github.com/spring-projects/spring-shell/releases)
- [Spring Shell v4 Migration Guide](https://github.com/spring-projects/spring-shell/wiki/v4-migration-guide)
