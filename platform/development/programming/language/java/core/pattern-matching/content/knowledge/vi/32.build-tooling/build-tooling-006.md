# Checkstyle và quy ước pattern trong Java 21

## 1. Mục tiêu

Trong nhóm **Build và tooling**, việc áp dụng pattern matching không dừng ở chỗ code biên dịch được. Một codebase có nhiều người cùng viết cần **quy ước thống nhất** cho tên pattern variable, cách xuống dòng với `instanceof` / record pattern, cách trình bày guard `when`, xử lý nhánh `switch` và những chỗ không nên lạm dụng deconstruction.

**Checkstyle** là công cụ phân tích tĩnh chủ yếu nhằm kiểm tra **phong cách và một số thực hành coding**. Nó có các check dành riêng cho pattern variables và cú pháp Java hiện đại, nhưng **không thay thế `javac`, unit tests hoặc code review về hành vi**.

Sau bài này, bạn sẽ biết:

- Thiết lập một cấu hình Checkstyle có thể áp dụng cho dự án Java 21, dùng đúng tên các module và phạm vi hỗ trợ của chúng.
- Quy định pattern variable theo `lowerCamelCase` và hạn chế gán lại biến đã được bind.
- Định dạng `instanceof`, record patterns, `switch`, `when` cho dễ đọc, không “code golf”.
- Phân biệt quy tắc style với các lỗi mà compiler kiểm tra: kiểu, scope, dominance, exhaustiveness và `null`.
- Tích hợp Checkstyle vào Gradle, Maven hoặc CLI, và đọc đúng ý nghĩa của kết quả kiểm tra.
- Xây checklist review pattern matching mà công cụ chưa thể tự động kết luận hoàn toàn.

**Phiên bản ví dụ:** Java 21, Checkstyle **14.3.0** là phiên bản minh họa đã chọn cho file cấu hình. Nhánh Checkstyle 14.x yêu cầu **JDK 21 trở lên để chạy Checkstyle**. Đây là **phiên bản ghim cho ví dụ**, không phải yêu cầu mọi dự án bắt buộc dùng chính xác phiên bản này. Với dự án có toolchain khác, cần chọn bản Checkstyle hỗ trợ cả cú pháp nguồn và JDK chạy analyzer.

## 2. Ba tầng kiểm tra nên tách riêng

Một pipeline chất lượng nên phân định rõ:

| Công cụ / tầng | Có trách nhiệm kiểm tra | Không thể tự kết luận |
|---|---|---|
| **`javac --release 21`** | Cú pháp, kiểu, phạm vi pattern variables, một số quy tắc dominance/exhaustiveness của `switch` | Style của tên biến, ý nghĩa nghiệp vụ của mỗi case |
| **Checkstyle** | Các quy tắc được cấu hình như tên biến, khoảng trắng, độ dài dòng, một số coding practices | Đầy đủ mọi giá trị `null`, tính đúng của guard, tính tương đương sau refactor |
| **Test và review** | Input thật, kết quả nghiệp vụ, nhánh fallback, `null`, boundary, bảo toàn hành vi | Không thể bảo đảm hết mọi trường hợp nếu dữ liệu và phạm vi test chưa đủ |

Ví dụ:

```java
if (input instanceof String DATA) {
    System.out.println(DATA);
}
```

Đoạn trên có thể **biên dịch hợp lệ**, nhưng với quy ước pattern variable `lowerCamelCase`, tên `DATA` là một style violation. Checkstyle module `PatternVariableName` có thể phát hiện.

Ngược lại, đoạn:

```java
if (input instanceof String text || text.isBlank()) {
    System.out.println("text");
}
```

là ví dụ **không hợp lệ về flow scoping**: ở vế phải của `||`, `text` có thể chưa được bind. Trước khi tranh luận về formatting, phải để compiler loại lỗi này.

**Thứ tự kiểm tra hợp lý:** build với compiler đúng Java version → chạy Checkstyle → chạy unit/integration tests → review các quyết định domain mà máy không đủ ngữ cảnh để chứng minh.

## 3. Các check liên quan trực tiếp đến pattern matching

Checkstyle được cấu hình bằng các **module**. Không phải tên nào nghe có vẻ hợp lý cũng tồn tại; hãy dùng tên và phạm vi thật từ tài liệu Checkstyle.

| Module | Mục đích và lưu ý | Mốc có trong Checkstyle |
|---|---|---|
| **`PatternVariableName`** | Kiểm tra tên pattern variables theo regex `format`. Khác với `LocalVariableName`, vốn không xử lý pattern variables | 8.36 |
| **`PatternVariableAssignment`** | Báo khi gán lại pattern variable đã bind, để tránh biến bị đổi ý nghĩa sau match | 10.26.0 |
| **`WhitespaceAround`** | Kiểm tra khoảng trắng quanh một tập token hỗ trợ; có token `LITERAL_WHEN`, nhưng cần đọc giới hạn của check đối với các switch expressions | Check lâu đời, token hỗ trợ tùy phiên bản |
| **`LineLength`** | Kiểm tra độ dài dòng; hữu ích với nested record patterns và guard dài | Check lâu đời |
| **`MissingSwitchDefault`** | Kiểm tra thiếu `default` ở **một số switch statements truyền thống**. **Không kiểm tra switch expressions hoặc switch statements dùng pattern/null labels**, vì compiler đã có kiểm tra exhaustive tương ứng | 3.1 |
| **`WhenShouldBeUsed`** *(tùy chọn)* | Phát hiện pattern case có một `if` đơn trong block mà có thể biểu đạt rõ bằng guard `when` | 10.18.0 |

Các module nêu trên có tài liệu chính thức trong phần tham khảo. **Không phải mọi quy tắc đều cần bật trong mọi dự án.** Ví dụ `WhenShouldBeUsed` thể hiện sở thích về cách viết guard; nên thảo luận trong team trước khi áp dụng hàng loạt, nhất là khi `if` có effect, `else` hoặc logic cần bảo toàn thứ tự.

### 3.1. Vì sao không chỉ dùng LocalVariableName?

Trong Checkstyle, `LocalVariableName` được thiết kế cho biến local thông thường và **không kiểm tra pattern variables**. Muốn bắt:

```java
if (value instanceof String CUSTOMER_ID) {
    // Tên pattern variable theo ALL_CAPS, không hợp quy ước này.
}
```

cần `PatternVariableName`. Nếu chỉ bật `LocalVariableName`, team có thể tưởng bộ quy tắc đặt tên đã bao phủ cả cú pháp pattern mới, trong khi thực tế chưa.

### 3.2. Vì sao PatternVariableAssignment hữu ích dù javac cho phép?

Từ Java 16, pattern variables **không mặc nhiên là final**. Vì thế đoạn sau là cú pháp hợp lệ:

```java
if (value instanceof String text) {
    text = text.trim();
    System.out.println(text);
}
```

Nhưng khi `text` bị gán lại, người đọc có thể tưởng nó vẫn đại diện đúng giá trị vừa khớp. `PatternVariableAssignment` giúp team cấm kiểu viết này ở tầng style. Cách dễ hiểu hơn:

```java
if (value instanceof String text) {
    String normalizedText = text.trim();
    System.out.println(normalizedText);
}
```

Đây là **lựa chọn quy ước**, không phải tuyên bố `javac` bắt buộc biến pattern phải `final`.

## 4. Tệp checkstyle.xml cho Java 21

Giả sử dự án có cấu trúc:

```text
project/
├── build.gradle               # hoặc pom.xml
├── config/
│   └── checkstyle/
│       └── checkstyle.xml
└── src/
    └── main/
        └── java/
            └── ...
```

Tạo tệp **`config/checkstyle/checkstyle.xml`**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">
<module name="Checker">
    <property name="charset" value="UTF-8"/>

    <module name="LineLength">
        <property name="max" value="100"/>
    </module>

    <module name="TreeWalker">
        <module name="PatternVariableName">
            <property name="format" value="^[a-z][a-zA-Z0-9]*$"/>
        </module>
        <module name="PatternVariableAssignment"/>
        <module name="WhitespaceAround"/>
        <module name="MissingSwitchDefault"/>
    </module>
</module>
```

### Giải thích chính xác từng phần

- **`Checker`** là module gốc. `LineLength` được đặt **trực tiếp trong Checker**, không phải bên trong `TreeWalker`.
- **`TreeWalker`** chứa các check cần phân tích cú pháp Java, như `PatternVariableName` và `PatternVariableAssignment`.
- Regex `^[a-z][a-zA-Z0-9]*$` là một lựa chọn **khá chặt**: tên pattern bắt đầu bằng chữ thường ASCII, sau đó là chữ/digit, không cho underscore hoặc toàn chữ hoa. Team có thể chọn regex khác nếu quy ước dự án yêu cầu.
- **`WhitespaceAround`** áp dụng bộ token mặc định của Checkstyle; không có nghĩa nó là formatter toàn bộ `switch`.
- **`MissingSwitchDefault`** được giữ nhằm minh họa một check truyền thống; đừng hiểu sai rằng việc bật nó đồng nghĩa phải thêm `default` vào mọi `switch expression` hoặc pattern `switch`.

Cấu hình XML trên đã được kiểm tra **đúng cú pháp XML** và xác nhận cây module dự kiến; phần **chạy Checkstyle thật** vẫn cần tải/phụ thuộc đúng phiên bản công cụ và chạy một trong các lệnh ở mục 8. Mẫu này không buộc mọi project phải thay thế toàn bộ bộ style đang dùng; nếu project đã có `google_checks.xml` hoặc quy tắc nội bộ, hãy **ghép có chủ đích** để tránh check trùng hoặc mâu thuẫn.

**Lưu ý về version:** `PatternVariableAssignment` chỉ có từ Checkstyle **10.26.0**; một bản Checkstyle quá cũ sẽ không nhận module này. Hơn nữa, parse support cho cú pháp Java 21 còn phụ thuộc phiên bản Checkstyle, không chỉ JDK chạy analyzer. Do đó cần ghim phiên bản Checkstyle trong build thay vì trông chờ bản mặc định của plugin.

## 5. Quy ước đặt tên pattern variables

Đặt tên là một phần của **API nhận thức** đối với người đọc: biến được bind trong nhánh là thứ bạn sẽ sử dụng tiếp.

**Nên viết:**

```java
if (input instanceof String customerId) {
    System.out.println(customerId);
}

if (input instanceof Integer retryCount) {
    System.out.println(retryCount);
}
```

**Không nên viết trong quy ước này:**

```java
if (input instanceof String CUSTOMER_ID) {
    System.out.println(CUSTOMER_ID);
}

if (input instanceof Integer retry_count) {
    System.out.println(retry_count);
}
```

Các đoạn đều minh họa **phần thân một phương thức có biến `input`**, không phải chương trình riêng. Với regex ở mục 4, `CUSTOMER_ID` và `retry_count` không hợp chuẩn tên pattern.

### Chọn tên biểu đạt vai trò, không chỉ hợp regex

`text`, `customerId`, `retryCount` và `request` thường giúp người đọc hiểu ngữ cảnh hơn các tên đơn chữ như `x`, `s`, `r` khi logic còn dài.

Trong record pattern:

```java
case Search(String query, int limit) when limit > 0 -> ...
```

`query` và `limit` thể hiện ý nghĩa component. Không cần đổi thành `a` / `b` chỉ vì một pattern đã ngắn. `PatternVariableName` có thể kiểm tra regex, nhưng **không thể tự đánh giá một cái tên có diễn đạt nghiệp vụ đủ tốt hay không**.

### Tránh shadowing và trùng tên

Nếu tên pattern gây xung đột phạm vi với biến khác, `javac` sẽ báo lỗi theo scope. Đây là lỗi ngôn ngữ, khác với check naming. Đừng chữa một lỗi shadowing chỉ bằng cách thêm hậu tố vô nghĩa; nên đặt tên theo vai trò của biến hoặc tách phạm vi xử lý để đọc rõ hơn.

## 6. Quy ước định dạng type, record và switch patterns

### 6.1. Giữ type pattern đơn giản ở một dòng

```java
if (input instanceof String text) {
    return text.trim();
}
```

Nếu có guard đơn giản, dùng `&&` với short-circuit:

```java
if (input instanceof String text && !text.isBlank()) {
    return text.trim();
}
```

Biến `text` chỉ được dùng khi pattern khớp. Với root `null`, `instanceof` trả false. Khi biểu thức dài, xuống dòng theo nhóm trách nhiệm chứ không nén mọi điều kiện vào một dòng.

### 6.2. Nested record pattern: xuống dòng theo tầng cấu trúc

Khi phải phân rã nhiều component:

```java
if (input instanceof Order(
        var orderId,
        Customer(var customerName, Address(var city, var country)),
        var total)
        && total >= 100
        && "VN".equals(country)) {
    return "READY:" + orderId;
}
```

**Đây là snippet minh họa**, giả định các record `Order`, `Customer`, `Address` đã được khai báo và phương thức trả `String`. Quy ước gợi ý:

- Tách các component lớn theo dòng, thụt lề nhất quán để thấy tầng record nào chứa tầng nào.
- Đặt tên component theo domain; đừng deconstruct những tầng không cần thiết.
- Canh các điều kiện `&&` dưới nhau, để thứ tự short-circuit có thể đọc được.
- Giữ các phép so sánh chuỗi **null-safe** như `"VN".equals(country)` khi component có thể null.
- Không coi các component tham chiếu là non-null chỉ vì record bên ngoài đã khớp.

**Không nên áp đặt một kiểu indent bằng regex đơn giản.** Checkstyle có những check whitespace/indentation, nhưng mức hỗ trợ cho từng AST token và phiên bản có thể khác nhau. Hãy chạy trực tiếp trên mã Java 21 thực tế, xem các vi phạm hợp lý rồi mới chốt quy tắc team.

### 6.3. Guard when: biểu thức ngắn và có tên

```java
case Search(String query, int limit)
        when query != null && !query.isBlank() && limit > 0
        -> "SEARCH:" + query.trim() + "/" + limit;
```

Nếu guard có nhiều ràng buộc nghiệp vụ hơn, thay vì ghép thêm sáu điều kiện trong `when`, nên cân nhắc phương thức như `isEligible(query, limit)`. Việc tách helper chỉ an toàn khi giữ thứ tự đánh giá, `null` và short-circuit.

**`WhenShouldBeUsed`** là một check tùy chọn có thể gợi ý đổi một `if` đơn trong block của pattern case thành guard `when`. Nhưng nó không thay con người quyết định việc dời điều kiện ra nhãn case có bảo toàn exception/side effects hay không.

### 6.4. Đừng ép thêm default vào sealed/enum switch expression

```java
sealed interface Request permits Search, Refresh {}

record Search(String query, int limit) implements Request {}
record Refresh(String target) implements Request {}
```

Với `switch expression` xử lý đủ hai loại, có thể liệt kê các nhánh cụ thể **mà không có `default`**. Khi bổ sung subtype mới, compiler có thể buộc cập nhật nơi xử lý — lợi thế của exhaustive checking.

Ngược lại, một `switch` trên `Object` có vô số loại giá trị thường **cần `default`** nếu không có type pattern bao phủ phần còn lại. Vì vậy quy tắc style “mọi switch phải có default” vừa thô vừa có thể khiến bỏ sót subtype mới.

**Phạm vi check thực tế:** Theo tài liệu Checkstyle, `MissingSwitchDefault` **không kiểm tra switch expressions**, và **không kiểm tra switch statements có pattern hoặc null labels**. Nó vẫn hữu ích cho một số traditional switch statements khác. Không cấu hình nhầm check này để thay thế exhaustiveness của compiler Java 21.

## 7. Chương trình Java 21 độc lập: ví dụ tuân thủ quy ước

Tạo tệp **`PatternStyleDemo.java`**:

```java
import java.util.Objects;

public class PatternStyleDemo {
    sealed interface Request permits Search, Refresh {}
    record Search(String query, int limit) implements Request {}
    record Refresh(String target) implements Request {}

    static String handle(Request request) {
        return switch (request) {
            case null -> "NULL_REQUEST";
            case Search(String query, int limit)
                    when query != null && !query.isBlank() && limit > 0
                    -> "SEARCH:" + query.trim() + "/" + limit;
            case Search(var query, var limit) -> "INVALID_SEARCH";
            case Refresh(var target)
                    when target != null && !target.isBlank()
                    -> "REFRESH:" + target.trim();
            case Refresh(var target) -> "INVALID_REFRESH";
        };
    }

    static String classify(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "TEXT:" + text.trim();
        }
        return "OTHER";
    }

    static void test(String label, String actual, String expected) {
        if (!Objects.equals(actual, expected)) {
            throw new AssertionError(
                    label + ": expected=" + expected + ", actual=" + actual);
        }
        System.out.println(label + " => " + actual);
    }

    public static void main(String[] args) {
        test("search good", handle(new Search("java", 3)), "SEARCH:java/3");
        test("search trimmed", handle(new Search(" java ", 1)), "SEARCH:java/1");
        test("search blank", handle(new Search("  ", 1)), "INVALID_SEARCH");
        test("search null", handle(new Search(null, 1)), "INVALID_SEARCH");
        test("limit zero", handle(new Search("java", 0)), "INVALID_SEARCH");
        test("limit negative", handle(new Search("java", -1)), "INVALID_SEARCH");
        test("refresh good", handle(new Refresh(" cache ")), "REFRESH:cache");
        test("refresh blank", handle(new Refresh(" ")), "INVALID_REFRESH");
        test("refresh null", handle(new Refresh(null)), "INVALID_REFRESH");
        test("request null", handle(null), "NULL_REQUEST");
        test("text", classify("hello"), "TEXT:hello");
        test("blank text", classify("  "), "OTHER");
        test("wrong type", classify(12), "OTHER");
        test("null type", classify(null), "OTHER");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 PatternStyleDemo.java
java PatternStyleDemo
```

**Stdout đã xác minh:**

```text
search good => SEARCH:java/3
search trimmed => SEARCH:java/1
search blank => INVALID_SEARCH
search null => INVALID_SEARCH
limit zero => INVALID_SEARCH
limit negative => INVALID_SEARCH
refresh good => REFRESH:cache
refresh blank => INVALID_REFRESH
refresh null => INVALID_REFRESH
request null => NULL_REQUEST
text => TEXT:hello
blank text => OTHER
wrong type => OTHER
null type => OTHER
```

Ví dụ đã được **biên dịch với `javac --release 21` và chạy thành công trên 14 tình huống**, mỗi kết quả đối chiếu với expected độc lập. Đây là **kiểm tra cú pháp và hành vi Java**, không thay cho việc chạy binary Checkstyle trên file này; cần chạy công cụ Checkstyle bằng lệnh ở mục 8 để xác định kết quả style thực tế của môi trường đó.

Những điểm style nổi bật:

- Pattern variables `query`, `limit`, `target` và `text` có tên diễn đạt vai trò, đúng `lowerCamelCase`.
- Không gán lại pattern variables; các giá trị `trim()` được dùng trực tiếp để tạo kết quả.
- `switch expression` bao phủ `Search` và `Refresh` bằng cặp guarded + fallback case cho từng loại, **không có `default`**. `case null` được khai báo riêng vì hợp đồng muốn trả `NULL_REQUEST`.
- Guard đặt kiểm tra `null` trước `isBlank()`; các trường hợp query/target null không ném NPE.
- `classify` minh họa `instanceof String text && ...` rõ ràng, không cần cast thủ công.
- Kết quả sai dữ liệu được kiểm tra bằng test, chứ không trông chờ Checkstyle xác thực logic.

## 8. Chạy Checkstyle trong project

Chọn **một** trong ba hình thức phù hợp với build đang có. Mã minh họa này giả định Java sources ở `src/main/java` và cấu hình ở `config/checkstyle/checkstyle.xml`. Nếu cấu trúc dự án khác, đổi các đường dẫn tương ứng.

### 8.1. Gradle với plugin Checkstyle

Thêm vào **`build.gradle`** (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'checkstyle'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

checkstyle {
    toolVersion = '14.3.0'
    configFile = file('config/checkstyle/checkstyle.xml')
}
```

Chạy trong project dùng Gradle Wrapper:

```bash
./gradlew checkstyleMain
./gradlew check
```

- `checkstyleMain` kiểm tra nguồn Java chính.
- `check` tích hợp các kiểm tra đã cấu hình, gồm Checkstyle và test theo mô hình Gradle.
- Chọn JDK chạy Checkstyle tương thích với phiên bản công cụ; **Checkstyle 14.x yêu cầu JDK 21+**. Ở một số dự án có toolchain đặc biệt, cần cấu hình launcher cho task Checkstyle riêng.
- Không coi `java.toolchain` là cách tự động bảo đảm mọi bản Gradle cũ đều nhận được Checkstyle 14.x; phải kiểm tra phiên bản wrapper và cấu hình công cụ thực tế.

Theo tài liệu Gradle, plugin Checkstyle có thể có **phiên bản analyzer mặc định** khác với phiên bản bạn cần; vì thế nên ghim `toolVersion` thay vì chỉ cài plugin rồi mặc định mọi check pattern mới đều được hỗ trợ.

### 8.2. Maven với Maven Checkstyle Plugin

Trong phần **`<build><plugins>`** của `pom.xml`, dùng một plugin entry:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-checkstyle-plugin</artifactId>
    <version>3.6.0</version>
    <configuration>
        <configLocation>config/checkstyle/checkstyle.xml</configLocation>
        <encoding>UTF-8</encoding>
        <consoleOutput>true</consoleOutput>
        <failsOnError>true</failsOnError>
    </configuration>
    <dependencies>
        <dependency>
            <groupId>com.puppycrawl.tools</groupId>
            <artifactId>checkstyle</artifactId>
            <version>14.3.0</version>
        </dependency>
    </dependencies>
    <executions>
        <execution>
            <id>checkstyle-verify</id>
            <phase>verify</phase>
            <goals>
                <goal>check</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

**Đây là fragment cho file `pom.xml`**, không phải một `pom.xml` hoàn chỉnh. Plugin Maven và thư viện Checkstyle có **vòng phát hành độc lập**: nếu không chỉ định dependency Checkstyle, plugin có thể chạy phiên bản Checkstyle bundled cũ hơn và không nhận module hoặc cú pháp Java 21 bạn định áp dụng.

Chạy:

```bash
./mvnw checkstyle:check
./mvnw verify
```

Nếu không dùng Maven Wrapper, thay `./mvnw` bằng `mvn`. Phase `verify` trong cấu hình sẽ chạy mục tiêu `check` cùng với vòng đời build. Chạy trên JDK tương thích với bản Checkstyle đã ghim; nếu build dùng một JDK khác, phải thiết kế toolchain/execution tương ứng.

**Lưu ý:** cấu hình minh họa có `failsOnError` để dừng khi công cụ gặp lỗi xử lý; hành vi làm build thất bại vì **style violations** còn chịu các thuộc tính goal như `failOnViolation` (mặc định của mục tiêu `check`). Trong hệ thống nghiêm ngặt, nên xác nhận các thuộc tính mong muốn từ tài liệu plugin và một lượt CI thật.

### 8.3. CLI không phụ thuộc Maven/Gradle

Nếu có tệp standalone Checkstyle JAR thích hợp, ví dụ `checkstyle-14.3.0-all.jar`, chạy:

```bash
java -jar checkstyle-14.3.0-all.jar \
    -c config/checkstyle/checkstyle.xml \
    src/main/java
```

Lệnh trên minh họa **shell Unix/Linux/macOS**; trên PowerShell có thể viết trên một dòng hoặc sử dụng backtick để tiếp dòng thay cho dấu `\`. Checkstyle kiểm tra toàn bộ các file Java trong thư mục được chỉ định; nếu dùng một file riêng, thay đường dẫn thư mục bằng đường dẫn file Java.

Đừng lưu bản JAR tự tải vào repository nếu dự án đã có giải pháp quản lý dependency qua Gradle/Maven. Cần xác minh nguồn tải artifact chính thức và kiểm soát phiên bản trong CI.

## 9. Từng loại vi phạm trông thế nào?

### 9.1. Tên pattern không đúng format

```java
if (input instanceof String STRING_VALUE) {
    System.out.println(STRING_VALUE);
}
```

Với cấu hình `PatternVariableName` ở mục 4, tên `STRING_VALUE` không khớp `^[a-z][a-zA-Z0-9]*$`. Sửa thành `stringValue`.

Đây là **style violation**, không phải ví dụ để chờ compiler báo sai cú pháp.

### 9.2. Gán lại biến pattern

```java
if (input instanceof String text) {
    text = text.trim();
}
```

`PatternVariableAssignment` báo về hành vi gán lại. Sửa:

```java
if (input instanceof String text) {
    String normalizedText = text.trim();
}
```

Mã thứ hai chỉ là minh họa cách tránh gán lại pattern variable; một bộ rules rộng hơn có thể báo biến local không dùng. Khi viết code production, hãy thật sự sử dụng `normalizedText`.

### 9.3. Biểu thức quá dài

```java
if (input instanceof String text && text != null && !text.isBlank() && text.length() >= 5 && text.startsWith("A")) {
    System.out.println(text);
}
```

Dù dòng đầu biên dịch được trong ngữ cảnh hợp lệ, nó khó đọc. `LineLength max=100` giúp phát hiện vấn đề cơ học. Trong ví dụ này, `text != null` là thừa vì root `instanceof String text` chỉ bind khi non-null, nhưng **Checkstyle không có nghĩa vụ tự chứng minh mọi kiểm tra null thừa**.

Sửa bằng cách chia điều kiện:

```java
if (input instanceof String text
        && !text.isBlank()
        && text.length() >= 5
        && text.startsWith("A")) {
    System.out.println(text);
}
```

Nếu còn nhiều điều kiện domain, tách thành phương thức có tên dễ hiểu thay vì xuống dòng mãi.

### 9.4. Dùng default theo thói quen

```java
return switch (request) {
    case Search(var query, var limit) -> "SEARCH";
    case Refresh(var target) -> "REFRESH";
    default -> "OTHER";
};
```

Giả sử `Request` là sealed type chỉ có `Search` và `Refresh`. `default` ở đây có thể làm mất tín hiệu khi người ta bổ sung subtype mới. Với closed-domain `switch expression`, nên cân nhắc **bỏ `default`** để `javac` buộc bổ sung case khi thay đổi type hierarchy.

Với nullable selector, vẫn cần chính sách rõ về `case null` hoặc exception. `default` thông thường không tự xử lý null trong pattern switch Java 21.

### 9.5. Không thấy lỗi Checkstyle nhưng code vẫn sai

Một đoạn style hoàn toàn đẹp:

```java
if (input instanceof String text && text.isBlank()) {
    return "VALID";
}
```

có thể sai nghiệp vụ nếu yêu cầu là “chỉ chấp nhận chuỗi không trắng”. Lỗi ở chỗ thiếu `!`, không phải whitespace hay tên pattern. Compiler lẫn Checkstyle có thể chấp nhận, nhưng test hành vi phải phát hiện.

## 10. Xử lý MissingSwitchDefault đúng cách

Đây là điểm hay gây hiểu nhầm giữa style và tính đúng của chương trình.

### Switch expression

```java
enum State { NEW, ACTIVE, CLOSED }

static String label(State state) {
    return switch (state) {
        case NEW -> "NEW";
        case ACTIVE -> "ACTIVE";
        case CLOSED -> "CLOSED";
    };
}
```

Compiler biết tập enum tại build time và có thể kiểm tra exhaustiveness. **Không cần thêm `default` chỉ vì quy tắc style chung**. Checkstyle `MissingSwitchDefault` hiện không kiểm tra switch expressions.

### Pattern switch statement

```java
static void logEvent(Object input) {
    switch (input) {
        case null -> System.out.println("null");
        case String text -> System.out.println("string:" + text);
        default -> System.out.println("other");
    }
}
```

Đây là phương thức minh họa độc lập, sử dụng pattern switch Java 21. Với những switch statements sử dụng pattern/null labels, Checkstyle `MissingSwitchDefault` cũng không áp check theo tài liệu hiện hành; compiler chịu trách nhiệm exhaustiveness theo quy tắc ngôn ngữ. Cần lưu ý việc *compiler exhaustive* không tự bảo đảm nhánh nào trả đúng thông điệp nghiệp vụ.

### Traditional switch statement

Với một traditional switch statement kiểu cũ, ví dụ:

```java
static void printLevel(int level) {
    switch (level) {
        case 1:
            System.out.println("low");
            break;
        case 2:
            System.out.println("high");
            break;
    }
}
```

các trạng thái ngoài 1/2 không được xử lý. Trong bối cảnh này, `MissingSwitchDefault` vẫn có lý do tồn tại để khuyến khích làm rõ fallback. **Không áp dụng kết luận này máy móc sang exhaustive switch expressions trên enum hoặc sealed hierarchy**.

## 11. Có nên bật WhenShouldBeUsed?

Checkstyle có module **`WhenShouldBeUsed`** từ phiên bản 10.18.0. Đây là ví dụ module chỉ dùng nếu team thống nhất:

```xml
<module name="WhenShouldBeUsed"/>
```

Dòng này được chèn **bên trong `TreeWalker`** của cấu hình.

Một pattern case có một `if` đơn trong block:

```java
case String text -> {
    if (text.isEmpty()) {
        System.out.println("empty text");
    }
}
```

có thể được gợi ý chuyển thành:

```java
case String text when text.isEmpty() -> {
    System.out.println("empty text");
}
```

Trong một `switch` có nhánh phù hợp khác, việc đổi từ hành động nằm trong block sang guard có thể **làm thay đổi nhánh được chọn** khi điều kiện false. Vì vậy **không tự động xem hai đoạn trên tương đương ngữ nghĩa trong mọi switch**. Cần xem toàn bộ thứ tự case và các nhánh fallback trước khi sửa. Đây là ví dụ rõ ràng cho thấy static style rule không thay thế behavioral review.

Không bật module này trên toàn bộ repository chỉ để làm tất cả case ngắn hơn. Có thể thử ở một module nhỏ, quan sát false positives/những trường hợp không nên refactor, rồi mới đưa vào CI.

## 12. Đưa Checkstyle vào CI như một quality gate

Một pipeline tối thiểu có thể là:

```text
Source code
    |
    +--> javac --release 21     -> lỗi cú pháp, kiểu, scope, exhaustiveness
    |
    +--> Checkstyle             -> vi phạm naming, assignment, whitespace, length
    |
    +--> Unit tests             -> null, guard, branch, boundary, output
    |
    +--> Code review            -> độ rõ ý nghĩa, policy domain, chi phí bảo trì
    |
    +--> Merge nếu các gate đạt và review được phê duyệt
```

**Thực hành nên có:**

- Ghim Checkstyle version và config trong repository để local/CI có cùng chính sách.
- Bảo đảm JDK chạy analyzer đủ mới, riêng Checkstyle 14.x cần **JDK 21+**.
- Bảo đảm compile/test sử dụng source target đúng: `--release 21` cho ví dụ record/pattern switch, không chỉ kiểm tra bằng javac trên một JDK mặc định.
- Nếu dự án có nhiều module Java 11/17/21, không áp dụng mù cùng một bộ rules Java 21 cho các module có toolchain cũ.
- Bắt đầu bằng một tập rule có tín hiệu tốt; tránh hàng trăm cảnh báo mới gây “noise”.
- Khi cần loại trừ ngoại lệ, ghi rõ lý do trong cấu hình suppression và review định kỳ, tránh vô hiệu hóa tất cả rule cho một thư mục lớn.
- Sử dụng formatter nhất quán nếu team cần tự động chỉnh định dạng; **Checkstyle chủ yếu báo lỗi style, không phải công cụ tự sửa mọi dòng code**.

### Khi build báo lỗi, phân loại trước khi sửa

| Triệu chứng | Loại vấn đề | Hướng xử lý |
|---|---|---|
| `javac` không nhận `case ... when ...` | Java source level/toolchain chưa phù hợp | Xác nhận `--release 21` và JDK |
| Checkstyle báo `Unable to create Root Module` hoặc không tìm thấy check | Analyzer quá cũ, sai tên module hoặc cấu hình XML | Kiểm tra bản Checkstyle và tên check |
| Checkstyle báo parse error ở record pattern | Bản analyzer chưa hỗ trợ cú pháp Java đang dùng hoặc source bị lỗi | Update analyzer; chạy `javac` để xác nhận mã nguồn |
| PatternVariableName báo tên `DATA` | Style naming | Đổi sang `data` hoặc điều chỉnh quy ước có chủ đích |
| PatternVariableAssignment báo gán lại `text` | Style/maintainability | Tạo biến mới cho giá trị đã xử lý |
| LineLength báo dòng dài | Formatting | Xuống dòng hoặc tách helper |
| Compiler báo dominated case | Quy tắc pattern switch | Xem lại thứ tự case rộng/hẹp |
| Compiler báo switch không exhaustive | Thiếu nhánh xử lý domain đóng | Thêm variant, **không tự thêm default để che lỗi** |
| Test báo NullPointerException với component lá | Runtime semantics | Kiểm tra nullable component và short-circuit |
| Test cho ra sai nhánh dù style sạch | Logic nghiệp vụ | Xem guard/fallback, expected và dữ liệu biên |

Một cảnh báo từ analyzer là tín hiệu cần phân tích, không phải lý do tự động sửa theo hướng làm đổi hành vi. Đặc biệt việc dời một `if` từ trong case block lên `when` hoặc việc bỏ `default` phải được xem trên toàn bộ switch.

## 13. Checklist quy ước pattern để review pull request

| Tiêu chí | Câu hỏi kiểm tra |
|---|---|
| **Tên biến** | Có theo quy ước `lowerCamelCase` và diễn đạt vai trò không? |
| **Gán lại** | Có sửa pattern variable sau bind không? Có thể dùng biến mới không? |
| **Độ sâu** | Có cần deconstruct từng nested record, hay type pattern nông rõ hơn? |
| **Null** | Root null, nested record null và component tham chiếu null có được xử lý đúng? |
| **Guard** | Có giữ đúng thứ tự `&&`/`||`, ngoặc và short-circuit? |
| **Scope** | Pattern variable chỉ được sử dụng nơi compiler bảo đảm đã match? |
| **Switch** | Nhánh có guard đứng trước nhánh tổng quát; fallback có đúng domain? |
| **Exhaustiveness** | Với enum/sealed type, có bỏ `default` khi cần compiler bắt variant mới? |
| **Formatting** | Tên, indent, độ dài dòng, khoảng trắng có theo team convention không? |
| **Tooling** | Checkstyle chạy bằng bản hỗ trợ cú pháp Java và JDK hiện tại không? |
| **Tests** | Có test kiểu sai, null, biên số, guard false, nhánh mới và expected độc lập? |

Dùng checklist này cùng kết quả Checkstyle: các check tự động giảm công sức review phần cơ học, còn reviewer tập trung vào **ý nghĩa nghiệp vụ** và các trường hợp công cụ không phân tích được.

## 14. Câu hỏi tự kiểm tra

**1. Java có biên dịch được `if (input instanceof String NAME)` không?**  
Có thể có, nếu input có kiểu phù hợp. Nếu Checkstyle cấu hình tên pattern lowerCamelCase, `NAME` là lỗi style, không phải lỗi type.

**2. Vì sao bật `LocalVariableName` chưa đủ để kiểm tra tên pattern variable?**  
Vì Checkstyle có `PatternVariableName` riêng; tài liệu `LocalVariableName` nói rõ nó không kiểm tra pattern variables.

**3. Có thể gán lại `text` sau khi `instanceof String text` match không?**  
Ngôn ngữ Java từ 16 cho phép trong scope thích hợp, nhưng Checkstyle `PatternVariableAssignment` có thể cấm theo chính sách readability.

**4. Bật `MissingSwitchDefault` có buộc thêm `default` vào switch expression trên enum không?**  
Không. Check này không kiểm tra switch expressions và cũng bỏ qua switch statements có pattern/null labels theo tài liệu hiện hành.

**5. Checkstyle có chứng minh guard `when query != null && !query.isBlank()` đúng nghiệp vụ không?**  
Không. Nó có thể kiểm tra một số style tokens, nhưng kiểm tra output và null vẫn cần test.

**6. Khi dùng Checkstyle 14.x, JDK nào chạy analyzer?**  
Tối thiểu JDK 21 theo thông tin tương thích của Checkstyle 14.x. Không nhầm JDK chạy analyzer với `--release` của mã nguồn.

**7. Vì sao nên ghim dependency Checkstyle khi dùng Maven plugin?**  
Vì plugin và thư viện analyzer có phiên bản riêng; bản bundled có thể quá cũ để hiểu cú pháp hoặc check Java 21.

**8. Có nên bật `WhenShouldBeUsed` rồi tự động chuyển mọi `if` trong case thành `when` không?**  
Không. Cần kiểm tra toàn bộ nhánh, fallback và thứ tự case; thay đổi có thể ảnh hưởng việc chọn nhánh.

**9. Nếu `javac` báo nhánh bị dominated nhưng Checkstyle chưa chạy, công cụ nào phải sửa trước?**  
Sửa cú pháp/ngữ nghĩa được compiler kiểm tra trước, sau đó chạy Checkstyle và tests.

**10. Nếu một pattern dài nhưng vẫn dưới 100 ký tự mỗi dòng, liệu quy ước đã đủ?**  
Chưa. Độ dài dòng không đo được độ phức tạp nhận thức; có thể cần domain method hoặc type pattern nông hơn.

## Kết luận

**Checkstyle giúp giữ quy ước pattern matching nhất quán, nhưng không thay compiler và test.** Với Java 21, hãy bắt đầu từ `PatternVariableName`, `PatternVariableAssignment` và một bộ whitespace/line length hợp lý; hiểu đúng phạm vi `MissingSwitchDefault` và xem `WhenShouldBeUsed` là chính sách tùy chọn. Ghim phiên bản analyzer tương thích với cú pháp Java đang dùng và tích hợp vào build để mọi người có cùng kết quả.

Mục tiêu không phải làm mọi pattern ngắn nhất, mà là **tên rõ nghĩa, cấu trúc dễ đọc, null/guard an toàn và các biến thể switch được xử lý có chủ đích**.

## Tài liệu tham khảo chính thức

- [Checkstyle — PatternVariableName](https://checkstyle.org/checks/naming/patternvariablename.html)
- [Checkstyle — PatternVariableAssignment](https://checkstyle.org/checks/coding/patternvariableassignment.html)
- [Checkstyle — LocalVariableName](https://checkstyle.org/checks/naming/localvariablename.html)
- [Checkstyle — WhitespaceAround](https://checkstyle.org/checks/whitespace/whitespacearound.html)
- [Checkstyle — LineLength](https://checkstyle.org/checks/sizes/linelength.html)
- [Checkstyle — MissingSwitchDefault](https://checkstyle.org/checks/coding/missingswitchdefault.html)
- [Checkstyle — WhenShouldBeUsed](https://checkstyle.org/checks/coding/whenshouldbeused.html)
- [Checkstyle — Versions and JDK Requirements](https://checkstyle.org/index.html)
- [Gradle — The Checkstyle Plugin](https://docs.gradle.org/current/userguide/checkstyle_plugin.html)
- [Apache Maven — Maven Checkstyle Plugin](https://maven.apache.org/plugins/maven-checkstyle-plugin/)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
