# Tắt DocLint có kiểm soát trong Javadoc

## 1. DocLint là gì?

**DocLint** là bộ kiểm tra chất lượng documentation comment mà công cụ **javadoc** sử dụng khi tạo tài liệu API. Nó phát hiện những vấn đề như HTML sai cấu trúc, liên kết tới symbol không tồn tại, cú pháp Javadoc không hợp lệ và các phần tài liệu bắt buộc còn thiếu.

Ví dụ:

~~~java
/**
 * Adds two numbers.
 * @param left first value
 * @param right second value
 * @return the sum
 */
public int add(int left, int right) {
    return left + right;
}
~~~

DocLint kiểm tra cả nội dung trong comment lẫn một số yêu cầu tài liệu gắn với khai báo Java. Nhờ đó, Javadoc có thể phát hiện lỗi trước khi HTML documentation được phát hành.

Trong dự án cũ, có thể tồn tại nhiều comment chưa hoàn chỉnh hoặc HTML cũ không còn hợp lệ. Khi cần tiếp tục build trong lúc sửa dần tài liệu, có thể tắt một nhóm kiểm tra hoặc giới hạn việc tắt vào package cụ thể.

Mục tiêu của **tắt DocLint có kiểm soát** là chọn chính xác kiểm tra đang gây cản trở, giữ lại các kiểm tra có giá trị và làm rõ phạm vi source được miễn kiểm tra.

## 2. DocLint thuộc javadoc, không phải javac

Cần phân biệt hai công cụ:

| Công cụ | Vai trò |
|---|---|
| javac | Biên dịch source Java thành bytecode và kiểm tra lỗi ngôn ngữ, kiểu dữ liệu, symbol cùng các điều kiện biên dịch. |
| javadoc | Đọc source và documentation comment để tạo HTML API documentation; DocLint kiểm tra comment trong quá trình này. |

Ví dụ, lệnh:

~~~bash
javac --release 17 -d out src/demo/Calculator.java
~~~

biên dịch source. Tùy chọn DocLint không phải là cách tắt kiểm tra kiểu hoặc lỗi cú pháp Java của javac.

Lệnh:

~~~bash
javadoc -d docs src/demo/Calculator.java
~~~

tạo tài liệu HTML và thực hiện các kiểm tra documentation tương ứng.

Nếu javadoc thất bại do một liên kết sai, HTML không hợp lệ hoặc tag tài liệu thiếu, thay đổi tùy chọn javac sẽ không giải quyết đúng nguyên nhân. Cần điều chỉnh tùy chọn của javadoc hoặc sửa documentation comment.

## 3. Các nhóm kiểm tra DocLint

JDK hiện đại cung cấp các nhóm kiểm tra sau:

| Nhóm | Nội dung |
|---|---|
| accessibility | Kiểm tra một số vấn đề về khả năng tiếp cận trong nội dung HTML của tài liệu. |
| html | Kiểm tra HTML tag, attribute và cấu trúc HTML trong documentation comment. |
| missing | Kiểm tra documentation comment hoặc các tag tài liệu cần thiết còn thiếu, ví dụ @param và @return. |
| reference | Kiểm tra reference như @see, {@link}, {@linkplain}, {@value} và các liên kết đến type/member. |
| syntax | Kiểm tra cú pháp Javadoc, bao gồm inline tag và các tag không hợp lệ. |

Từ khóa **all** đại diện cho tất cả nhóm kiểm tra. Từ khóa **none** tắt các nhóm DocLint.

Một lỗi HTML như tag không đóng có thể được báo ở nhóm html. Một reference tới class không tồn tại thuộc nhóm reference. Một method thiếu @return hoặc @param thuộc nhóm missing.

Phân biệt nhóm giúp tránh tắt toàn bộ DocLint khi chỉ có một loại comment cần được xử lý.

## 4. Cú pháp điều khiển DocLint

Các tùy chọn DocLint được truyền trực tiếp cho javadoc:

~~~bash
-Xdoclint
-Xdoclint:all
-Xdoclint:none
-Xdoclint:<group>
-Xdoclint:all,-<group>
~~~

Ý nghĩa:

- **-Xdoclint:** bật các kiểm tra được khuyến nghị.
- **-Xdoclint:all:** bật tất cả nhóm kiểm tra.
- **-Xdoclint:none:** tắt toàn bộ nhóm kiểm tra DocLint.
- **-Xdoclint:html:** chỉ bật nhóm html.
- **-Xdoclint:all,-missing:** bật tất cả nhóm ngoại trừ missing.
- **-Xdoclint:all,-reference:** bật tất cả nhóm ngoại trừ reference.

Có thể chọn nhiều nhóm, phân tách bằng dấu phẩy:

~~~bash
javadoc -Xdoclint:html,syntax -d docs src/demo/Calculator.java
~~~

Lệnh trên chỉ bật kiểm tra HTML và cú pháp Javadoc trong lần tạo tài liệu đó.

Để giữ hầu hết kiểm tra nhưng tạm bỏ kiểm tra reference:

~~~bash
javadoc -Xdoclint:all,-reference -d docs src/demo/Calculator.java
~~~

Dấu trừ đứng trước tên nhóm có nghĩa là tắt nhóm đó trong tập kiểm tra đã chọn. Cú pháp nhóm có thể kết hợp với tùy chọn giới hạn package ở phần sau.

Các tùy chọn bắt đầu bằng -X là tùy chọn mở rộng, không phải giao diện chuẩn được cam kết ổn định lâu dài. Hãy kiểm tra **javadoc -X** trên đúng JDK được dùng để build.

## 5. Tắt riêng nhóm missing

Một tình huống thường gặp là source cũ chưa có đủ @param, @return hoặc documentation comment cho mọi API public. Nếu HTML và reference đã tốt, có thể tắt riêng nhóm missing:

~~~bash
javadoc -Xdoclint:all,-missing -d docs src/demo/api/Calculator.java
~~~

Cách này giữ lại các kiểm tra:

- HTML.
- Reference.
- Syntax.
- Accessibility.

Chỉ nhóm missing được loại khỏi lần kiểm tra đó.

Ví dụ source:

~~~java
package demo.api;

/**
 * Performs a calculation.
 */
public class Calculator {
    /**
     * Adds two numbers.
     */
    public int add(int left, int right) {
        return left + right;
    }
}
~~~

Method add chưa có @param và @return. Với tùy chọn -Xdoclint:all,-missing, Javadoc có thể tạo tài liệu mà không phát cảnh báo thuộc nhóm missing cho method này; các nhóm kiểm tra còn lại vẫn hoạt động.

Lệnh kiểm tra:

~~~bash
javadoc -Xdoclint:all,-missing -d docs src/demo/api/Calculator.java
~~~

Kết quả kiểm tra với JDK 24.0.2: lệnh kết thúc với exit code 0 và tạo file docs/demo/api/Calculator.html.

Đây là lựa chọn phù hợp khi nhóm đang bổ sung documentation theo từng đợt nhưng vẫn muốn duy trì kiểm tra HTML, reference và cú pháp.

Không nên mặc định tắt missing vĩnh viễn cho toàn bộ API. Các tag @param, @return và @throws giúp người dùng hiểu contract của method, đặc biệt với thư viện công khai.

## 6. Tắt DocLint cho một package cụ thể

Nếu chỉ một package legacy có comment chưa đạt chuẩn, có thể giới hạn phạm vi miễn kiểm tra bằng tùy chọn package:

~~~bash
-Xdoclint/package:<packages>
~~~

Để tắt DocLint cho package **com.example.legacy**:

~~~bash
javadoc -Xdoclint:all \
    -Xdoclint/package:-com.example.legacy \
    -d docs \
    src/com/example/legacy/LegacyApi.java
~~~

Dấu trừ trước tên package có nghĩa là tắt kiểm tra cho package đó. Các package khác trong cùng lần chạy vẫn có thể được kiểm tra đầy đủ.

Ví dụ source legacy có HTML cũ:

~~~java
package com.example.legacy;

/**
 * <p>Old documentation with <b>an unclosed tag.
 * @see MissingType
 */
public class LegacyApi {
    /**
     * Returns a value.
     */
    public String value() {
        return "ok";
    }
}
~~~

Lệnh package-scoped suppression:

~~~bash
javadoc -Xdoclint:all \
    -Xdoclint/package:-com.example.legacy \
    -d docs \
    src/com/example/legacy/LegacyApi.java
~~~

Với JDK 24.0.2, thử nghiệm package suppression tạo được HTML và kết thúc với exit code 0 dù comment trong package có lỗi DocLint.

Nếu muốn áp dụng cho các package con, dùng package prefix với **.* **:

~~~bash
-Xdoclint/package:-com.example.legacy.*
~~~

Để chỉ định package cần bật kiểm tra, bỏ dấu trừ:

~~~bash
-Xdoclint/package:com.example.api.*
~~~

Tên package phải là tên đầy đủ. Package filter chỉ áp dụng cho những package được đưa vào lần chạy javadoc đó; nó không thay thế việc chọn source/package đầu vào.

## 7. Tắt toàn bộ DocLint bằng -Xdoclint:none

Khi cần tạo tài liệu tạm thời từ source legacy có quá nhiều vấn đề, có thể tắt tất cả nhóm DocLint:

~~~bash
javadoc -Xdoclint:none -d docs src/com/example/legacy/LegacyApi.java
~~~

Tùy chọn này tắt các kiểm tra DocLint về accessibility, HTML, missing, reference và syntax.

Chỉ nên dùng trong các trường hợp có phạm vi rõ ràng, chẳng hạn:

- Tạo tài liệu tạm để phục vụ migration.
- Tạo artifact nội bộ trong thời gian sửa một lượng lớn Javadoc cũ.
- Tách bước tạo tài liệu khỏi bước kiểm tra chất lượng trong một pipeline chuyển đổi có thời hạn.

**-Xdoclint:none không tắt mọi diagnostic của javadoc.** Javadoc vẫn có thể báo cảnh báo hoặc lỗi thuộc cơ chế khác. Ví dụ, thử nghiệm trên JDK 24.0.2 cho thấy reference không tìm thấy vẫn có thể được báo dưới dạng warning khi DocLint đã tắt.

Tùy chọn này cũng không bỏ qua lỗi đọc source, lỗi option, lỗi doclet hoặc lỗi cần thiết để tạo tài liệu. Vì vậy, không được hiểu rằng dùng -Xdoclint:none sẽ khiến mọi lần tạo Javadoc luôn thành công.

Nếu chỉ cần bỏ cảnh báo thiếu @param/@return, hãy chọn -Xdoclint:all,-missing. Nếu chỉ một package legacy có vấn đề, hãy dùng package-scoped suppression. Chỉ dùng -Xdoclint:none khi thực sự cần bỏ toàn bộ DocLint trong phạm vi build đã xác định.

## 8. Không nhầm DocLint suppression với các tùy chọn khác

Một số tùy chọn javadoc có vẻ liên quan đến warning hoặc output nhưng không có tác dụng tương đương:

| Tùy chọn | Tác dụng thực tế |
|---|---|
| -Xdoclint:none | Tắt các nhóm kiểm tra DocLint. |
| -Xdoclint:all,-missing | Tắt riêng nhóm missing và giữ các nhóm khác. |
| -quiet | Ẩn status message của javadoc; diagnostic vẫn có thể xuất hiện. |
| -Werror | Báo lỗi nếu có warning; không tắt kiểm tra. |
| -Xmaxwarns <number> | Giới hạn số warning được in; không làm cho source hết warning. |
| -Xmaxerrs <number> | Giới hạn số error được in; không sửa hoặc vô hiệu hóa nguyên nhân. |

Ví dụ:

~~~bash
javadoc -quiet -d docs src/demo/api/Calculator.java
~~~

-quiet chỉ giảm thông báo tiến trình như loading source hoặc generating page. Nó không phải lệnh tắt DocLint.

Nếu dùng -Werror:

~~~bash
javadoc -Xdoclint:none -Werror -d docs src/demo/api/Calculator.java
~~~

warning còn lại từ các cơ chế khác vẫn có thể khiến lệnh thất bại. Cần đọc diagnostic thực tế thay vì thêm -quiet hoặc tăng giới hạn warning để che vấn đề.

## 9. Ví dụ cấu hình chính sách DocLint cho API và legacy

Giả sử project có hai vùng source:

~~~text
src/
├── com/example/api/
│   └── Calculator.java
└── com/example/legacy/
    └── LegacyApi.java
~~~

Chính sách mong muốn:

- API mới phải tuân thủ tất cả nhóm DocLint.
- Package legacy tạm thời được miễn DocLint.
- Những package còn lại vẫn được kiểm tra.

Có thể chạy:

~~~bash
javadoc -Xdoclint:all \
    -Xdoclint/package:-com.example.legacy \
    -d docs \
    src/com/example/api/Calculator.java \
    src/com/example/legacy/LegacyApi.java
~~~

Khi chạy với nhiều source file, hãy chắc chắn tên package trong source khớp với package filter. Không nên thêm filter quá rộng như **-com.example.*** nếu chỉ muốn miễn một package nhỏ.

Nếu API mới chỉ thiếu tag mô tả nhưng các nhóm khác vẫn cần kiểm tra, một chính sách khác là:

~~~bash
javadoc -Xdoclint:all,-missing \
    -d docs \
    src/com/example/api/Calculator.java
~~~

Hai cách giải quyết hai vấn đề khác nhau: một cách giới hạn theo package, cách còn lại giới hạn theo loại kiểm tra. Chọn cách hẹp nhất phù hợp với nguyên nhân thực tế.

## 10. Dùng option file và tích hợp build tool

Khi lệnh javadoc dài, có thể đặt option vào argument file.

File **javadoc.options**:

~~~text
-Xdoclint:all,-missing
-encoding
UTF-8
-d
docs
src/demo/api/Calculator.java
~~~

Chạy:

~~~bash
javadoc @javadoc.options
~~~

Javadoc đọc option và tên file từ argument file. Cách này giúp lưu cấu hình cùng project, dễ review thay đổi và tránh lặp lệnh dài trong CI.

### Maven

Với maven-javadoc-plugin, truyền DocLint option qua cấu hình additional options của plugin. Ví dụ:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <configuration>
        <additionalOptions>
            <additionalOption>-Xdoclint:all,-missing</additionalOption>
        </additionalOptions>
    </configuration>
</plugin>
~~~

Tên parameter và cách chuyển tiếp option phụ thuộc phiên bản plugin. Sau khi cấu hình, hãy chạy goal Javadoc và kiểm tra log thực tế để xác nhận option đã được truyền tới javadoc.

### Gradle

Với Gradle Javadoc task, có thể thêm option vào StandardJavadocDocletOptions:

~~~groovy
tasks.withType(Javadoc).configureEach {
    options.addBooleanOption('Xdoclint:all,-missing', true)
}
~~~

Kiểm tra Gradle version và JDK toolchain mà task đang dùng. JDK chạy Gradle daemon và JDK được chọn cho Javadoc task có thể khác nhau.

Không nên đặt cấu hình DocLint ở nhiều tầng mà không rõ option nào có hiệu lực. Hãy giữ một nguồn cấu hình chính cho local build và CI, rồi kiểm tra command line của task khi cần chẩn đoán.

## 11. Kết hợp DocLint với classpath và module path

Một số diagnostic reference không xuất hiện vì javadoc không tìm được dependency hoặc module cần thiết. Trước khi tắt nhóm reference, hãy xác minh môi trường phân giải symbol.

Với thư viện trên classpath:

~~~bash
javadoc \
    -classpath "lib/api-dependency.jar" \
    -Xdoclint:all \
    -d docs \
    src/com/example/api/Service.java
~~~

Với module:

~~~bash
javadoc \
    --module-path mods \
    --module com.example.api \
    -Xdoclint:all \
    -d docs
~~~

Nếu reference tới một type có thật nhưng javadoc không tìm thấy, kiểm tra classpath, module path, source path và module được đưa vào lệnh. Tắt reference có thể làm build chạy tiếp nhưng tài liệu sinh ra vẫn có liên kết thiếu hoặc không chính xác.

Đối với liên kết tới tài liệu API bên ngoài, kiểm tra các tùy chọn như -link hoặc -linkoffline và URL/package list tương ứng. Không nên tắt reference chỉ vì cấu hình external documentation chưa đúng.

## 12. Diagnostic, exit code và -Werror

DocLint có thể báo lỗi hoặc cảnh báo tùy loại vấn đề và phiên bản JDK. Một lỗi HTML nghiêm trọng hoặc reference không thể giải quyết có thể làm javadoc kết thúc với exit code khác 0. Một số thiếu sót tài liệu có thể được báo dưới dạng warning.

Có thể yêu cầu javadoc xem mọi warning là lỗi:

~~~bash
javadoc -Xdoclint:all -Werror -d docs src/demo/api/Calculator.java
~~~

Đây là chính sách nghiêm ngặt, phù hợp với API đã được chuẩn hóa tài liệu. Nếu đang migrate code cũ, có thể tạm dùng một nhóm suppression cụ thể rồi bỏ suppression khi hoàn tất.

Trong CI, nên ghi nhận:

- JDK version và javadoc version.
- Các DocLint group đang bật/tắt.
- Package được miễn kiểm tra nếu có.
- Warning/error đầu tiên và source line liên quan.
- Exit code của javadoc.
- Thư mục HTML được tạo và artifact được phát hành.

Không chỉ dựa vào việc thư mục docs tồn tại. Javadoc có thể tạo một phần HTML rồi kết thúc với lỗi. Exit code và diagnostic là bằng chứng quan trọng để xác định build đã thành công hay chưa.

## 13. Quy trình xử lý DocLint có kiểm soát

Khi gặp lỗi DocLint trong một dự án, thực hiện theo thứ tự:

1. Chạy lại javadoc với log đủ rõ để xác định file, dòng và loại diagnostic.
2. Phân loại vấn đề vào html, reference, missing, syntax hoặc accessibility.
3. Kiểm tra xem lỗi do source comment hay do thiếu classpath/module path.
4. Nếu có thể, sửa comment hoặc reference trực tiếp.
5. Nếu cần migration, chọn nhóm nhỏ nhất bằng -Xdoclint:all,-group.
6. Nếu chỉ một package legacy có vấn đề, giới hạn suppression bằng -Xdoclint/package:-package.name.
7. Chỉ dùng -Xdoclint:none khi có lý do cần tắt toàn bộ DocLint trong một build cụ thể.
8. Ghi rõ phạm vi, người chịu trách nhiệm và thời điểm bỏ suppression.
9. Chạy lại Javadoc trên API mới để xác nhận các nhóm kiểm tra còn lại vẫn hoạt động.
10. Khi migration xong, bỏ suppression và bật lại -Xdoclint:all.

Một suppression tốt cần trả lời được ba câu hỏi: vì sao cần tắt, tắt đúng phạm vi nào và điều kiện nào để bật lại. Điều này giúp tránh biến giải pháp tạm thời thành chính sách vĩnh viễn.

## 14. Lỗi thường gặp khi tắt DocLint

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| -Xdoclint:none nhưng vẫn có warning | Warning không thuộc DocLint, ví dụ reference diagnostic của Javadoc. | Đọc loại diagnostic và xử lý nguyên nhân riêng. |
| -Xdoclint:all,-missing vẫn báo lỗi HTML | Chỉ nhóm missing bị tắt; nhóm html vẫn hoạt động. | Sửa HTML hoặc cân nhắc suppression hẹp khác nếu có lý do. |
| Package legacy vẫn bị kiểm tra | Tên package filter không khớp package trong source hoặc filter quá hẹp. | Kiểm tra fully qualified package và dùng .* cho subpackages khi cần. |
| Không còn cảnh báo @param/@return | Nhóm missing đã bị tắt. | Bổ sung tag tài liệu rồi bật lại nhóm missing. |
| Javadoc không tìm thấy class trong @see | Classpath/module path hoặc source path chưa đúng. | Cấu hình dependency và external links trước khi tắt reference. |
| -quiet vẫn hiện lỗi | -quiet chỉ ẩn status message. | Dùng DocLint option đúng nhóm; không dùng quiet để thay thế. |
| -Werror vẫn làm build thất bại | Vẫn còn warning từ nhóm đang bật hoặc từ Javadoc khác. | Xử lý warning còn lại hoặc điều chỉnh chính sách có kiểm soát. |
| Build local thành công nhưng CI thất bại | JDK/plugin/toolchain hoặc DocLint option khác nhau. | Đồng bộ JDK version và option trong build configuration. |
| Package khác cũng bị miễn kiểm tra | Dùng package prefix quá rộng. | Giới hạn filter vào đúng package legacy. |
| Tài liệu sinh ra có liên kết thiếu | Đã tắt reference check hoặc không cấu hình external docs. | Khôi phục reference check và cấu hình classpath/link phù hợp. |

## 15. Checklist trước khi tắt DocLint

- [ ] Đã xác định diagnostic thuộc nhóm DocLint nào.
- [ ] Đã phân biệt lỗi Javadoc với lỗi biên dịch javac.
- [ ] Đã kiểm tra classpath, module path và external documentation links.
- [ ] Đã ưu tiên sửa documentation comment nếu có thể.
- [ ] Đã chọn đúng nhóm cần tắt bằng -Xdoclint:all,-group.
- [ ] Đã giới hạn theo package nếu vấn đề chỉ nằm trong code legacy.
- [ ] Đã hiểu -Xdoclint:none chỉ tắt DocLint, không tắt mọi Javadoc diagnostic.
- [ ] Đã không dùng -quiet hoặc -Xmaxwarns như cách tắt kiểm tra.
- [ ] Đã xem xét tác động của -Werror đối với warning còn lại.
- [ ] Đã kiểm tra option trên đúng JDK version của local build và CI.
- [ ] Đã ghi rõ lý do và điều kiện bật lại kiểm tra.
- [ ] Đã lên kế hoạch loại bỏ suppression sau khi migration hoàn tất.

Tắt DocLint có kiểm soát giúp dự án tiếp tục tạo Javadoc trong khi xử lý tài liệu cũ. Bằng cách chọn đúng nhóm hoặc package, giữ các kiểm tra còn lại và theo dõi exit code, nhóm có thể giảm trở ngại của migration mà vẫn bảo vệ chất lượng API documentation.