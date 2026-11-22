# Đọc coverage theo nhánh pattern trong Java 21+: `switch`, `when`, record và `null`

## 1. Mục tiêu: đo đường đi thực thi, không chỉ xem dòng đã chạy

Trong chương trình Java 21 dùng **pattern matching**, một khối `switch` có thể chứa nhiều **type patterns**, **record patterns**, **guard `when`**, nhánh `case null` và nhánh dự phòng. Khi chạy test, hai câu hỏi khác nhau cần được trả lời:

1. **Line coverage:** dòng mã đó đã từng được thực thi chưa?
2. **Branch coverage (C1):** những nhánh điều khiển do compiler sinh ra cho các quyết định `if`/`switch` đã được test đi qua bao nhiêu?

Một dòng màu xanh trong báo cáo coverage không chứng minh mọi điều kiện của pattern đã được kiểm thử. Ngược lại, một `case` được chạy **một lần** chưa chắc đã kiểm tra hết kết quả đúng/sai của guard, kết quả không khớp của nested record pattern hoặc đường đi dự phòng.

Bài này hướng dẫn đọc coverage đúng ở mức **nhánh pattern**, lập ma trận test cho từng loại dữ liệu, hiểu màu trong báo cáo JaCoCo và tránh nhầm giữa **nhánh nghiệp vụ** với **nhánh bytecode** do trình biên dịch tạo ra.

Phạm vi: Java **21+** (pattern matching for `switch` và record patterns đã ổn định), kiểm thử qua JUnit 5 và đo coverage bằng JaCoCo. Các con số phần trăm trong ví dụ minh họa phải được lấy từ **báo cáo thực tế**; không suy đoán % chỉ bằng việc đếm nhãn `case`.

## 2. Coverage theo nhánh trong JaCoCo là gì?

JaCoCo là công cụ đo mã Java đã được chạy khi test. Các bộ đếm phổ biến:

| Bộ đếm | Đang đo | Khi nào có ích? |
| --- | --- | --- |
| **Instructions (C0)** | Số chỉ thị bytecode được/không được thực thi | Quan sát mức chạy của các khối lệnh |
| **Lines** | Dòng nguồn có thông tin debug được ánh xạ từ bytecode | Xem dòng nào bị bỏ qua |
| **Branches (C1)** | Các nhánh của quyết định `if` và `switch` theo bytecode | Kiểm tra đường đúng/sai và lựa chọn ở switch |
| **Methods** | Phương thức được thực thi | Phát hiện phương thức hoàn toàn chưa chạy |
| **Complexity** | Độ phức tạp chu trình từ control-flow được JaCoCo tính | Xem còn đường ra quyết định nào chưa kiểm tra |

Về ý nghĩa toán học:

~~~text
Branch coverage (%) =
    100 × (số nhánh đã chạy / tổng số nhánh được đo)
~~~

Nếu một report hiển thị **14 covered / 16 total**, tỷ lệ là **87,5%**. Đây chỉ là ví dụ số học để giải thích cách đọc cột, **không** phải tỷ lệ đã đo của chương trình trong bài.

JaCoCo xác định các nhánh từ **bytecode** sau khi biên dịch. Một nhãn `case` trong source có thể dẫn đến nhiều quyết định nội bộ (phép kiểm tra kiểu, kiểm tra guard, dịch chuyển đến nhánh khác); số nhánh JaCoCo báo **không bắt buộc bằng** số dòng `case` hay số nhánh bạn đếm bằng mắt.

**Chú ý về exception:** theo định nghĩa bộ đếm JaCoCo, luồng xử lý exception **không được tính là branch C1**. Vì thế branch coverage cao hoặc 100% không chứng minh bạn đã test toàn bộ các lỗi, exception, input null không hợp lệ hay trường hợp bất thường của nghiệp vụ.

## 3. Cách đọc các dấu hiệu trên báo cáo HTML

Trong báo cáo HTML JaCoCo, chỉ số `Missed Branches` và `Cov.` ở cấp package/class/method cho biết còn nhánh chưa chạy. Khi mở trang source (nếu có thông tin debug), JaCoCo dùng **hình thoi** tại các dòng có nhánh:

- **Hình thoi đỏ:** không nhánh nào tại điểm quyết định đó được chạy.
- **Hình thoi vàng:** **mới chạy một phần** các nhánh ở điểm đó.
- **Hình thoi xanh:** tất cả các nhánh JaCoCo nhận diện ở điểm đó đã được chạy.

Màu nền dòng mã là một lớp thông tin khác về instruction coverage. Nếu dòng `case String s when s.isBlank() -> ...` được tô xanh ở phần thân, điều đó chỉ nói code ở thân đã chạy; bạn vẫn cần xem **hình thoi/cột missed branches** và ma trận ca kiểm thử để kết luận về các đường vào/ra của guard.

**Cách đọc thực tế:**

1. Mở tổng quan của module/package: xác định class nào có `Missed Branches` nhiều.
2. Vào method chứa `switch` pattern matching.
3. Mở source, xem các hình thoi ở dòng `switch`, `when` và quyết định liên quan.
4. Đối chiếu với **test input cụ thể** để biết nhánh nào chưa đi qua.
5. Bổ sung test với giá trị làm đổi điều kiện hoặc tạo trường hợp không khớp.
6. Chạy lại test + report, so sánh thay đổi. Không “tăng %” bằng cách xóa điều kiện hoặc thêm `default` che lỗi logic.

Nếu không có thông tin dòng nguồn phù hợp, chỉ số C1 vẫn có thể được tính nhưng giao diện ánh xạ sang đúng dòng source sẽ hạn chế.

## 4. Hiểu các đường đi của type pattern và guard `when`

Ví dụ Java 21:

~~~java
static String classify(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.isBlank() -> "BLANK";
        case String s -> "TEXT:" + s;
        default -> "OTHER";
    };
}
~~~

Các đường đi nghiệp vụ nên kiểm tra:

| Đầu vào | Nhánh được chọn | Điều đang chứng minh |
| --- | --- | --- |
| `null` | `case null` | Có chính sách xử lý null |
| `"   "` | `String s when s.isBlank()` | Type pattern khớp, guard đúng |
| `"Java"` | `String s` | Type pattern khớp, guard sai, chuyển nhánh String kế |
| `42` | `default` | Không khớp String, xử lý kiểu khác |

**Sai lầm:** chỉ test `classify("   ")`, thấy case có guard đã chạy rồi kết luận “đã phủ đủ case String”. Bạn còn thiếu trường hợp `String` thường để kiểm tra **guard false** và đường rơi sang `case String s` kế tiếp.

Guard chỉ được đánh giá **sau khi** pattern match thành công; guard không chạy với đầu vào không thuộc kiểu phù hợp. Vì vậy không nên đánh đồng “guard false” với “type pattern false”. Chúng là hai lý do khác nhau dẫn đến không chọn nhánh.

Đặt case có guard cụ thể trước case String tổng quát. Đặt `case String s` trước `case String s when ...` có thể gây lỗi **dominance** lúc biên dịch, không phải một nhánh runtime cần test.

## 5. Với `&&` và `||`, một case còn có nhiều điều kiện con

Một case có guard phức hợp:

~~~java
case TextJob(var text) when text == null || text.isBlank() ->
    "EMPTY_TEXT";
~~~

Để đọc coverage cho logic này, tối thiểu nên kiểm tra:

- `TextJob(null)`: `text == null` **true**; `text.isBlank()` **không chạy** vì `||` short-circuit.
- `TextJob("   ")`: điều kiện đầu false, `isBlank()` **true**.
- `TextJob("Java")`: cả hai vế false, nên case guard này không chọn; chuyển sang `case TextJob(var text)` thường.
- Giá trị không phải `TextJob`: type pattern không khớp; guard thậm chí không được chạy.

Tương tự:

~~~java
case ResizeJob(var width, var height)
        when width <= 0 || height <= 0 -> "INVALID_SIZE";
~~~

Đừng chỉ test `ResizeJob(0, 7)`. Khi `width <= 0` đúng, vế `height <= 0` bị bỏ qua. Thêm `ResizeJob(4, 0)` để kiểm tra trường hợp **vế thứ hai quyết định kết quả**, và `ResizeJob(4, 3)` để kiểm tra cả hai đều sai, dẫn đến nhánh valid.

Ở mức mã nguồn, đây là phương pháp **test các điều kiện con**. Ở mức JaCoCo, branch counter phụ thuộc bytecode biên dịch và bộ lọc report; không nên tự khẳng định “3 test thì đúng 100% C1” khi chưa chạy công cụ.

## 6. Record pattern lồng: tách đường khớp record, guard và component null

Giả sử:

~~~java
record Point(int x, int y) {}
record MoveJob(Point target) {}
~~~

Switch có hai pattern cùng loại nhưng độ cụ thể khác nhau:

~~~java
static String describe(Object value) {
    return switch (value) {
        case MoveJob(Point(var x, var y)) when x == y ->
            "DIAGONAL:" + x;
        case MoveJob(Point(var x, var y)) ->
            "MOVE:" + x + "," + y;
        case MoveJob(var target) ->
            "NO_TARGET";
        case null -> "NULL";
        default -> "OTHER";
    };
}
~~~

Nên test **ít nhất ba trạng thái**:

1. `MoveJob(new Point(2, 2))`: nested record `Point` khớp, guard `x == y` đúng → `DIAGONAL:2`.
2. `MoveJob(new Point(2, 5))`: nested record khớp, guard sai → case `Point` thứ hai → `MOVE:2,5`.
3. `MoveJob(null)`: selector bên ngoài **không null**, nhưng component `target` null nên nested `Point(...)` không khớp; case `MoveJob(var target)` được chọn → `NO_TARGET`.

Một điểm tinh tế: `case null` trong switch chỉ xử lý **selector null**, không thay thế phép kiểm tra null cho **component** của record. Nếu test chỉ có selector null mà không có component null, bạn vẫn thiếu đường đi nghiệp vụ quan trọng.

**Không đếm nhánh bằng tên pattern:** ba ca trên đi qua hai cấp deconstruction và một guard; trình biên dịch có thể sinh quyết định kiểm tra kiểu và null ở bytecode. JaCoCo có thể hiển thị những nhánh được lọc/tổng hợp khác với mô hình thủ công. Dùng test matrix để đánh giá **hành vi**, dùng JaCoCo C1 để quan sát **độ bao phủ bytecode**.

## 7. `sealed` + switch exhaustive không tự bảo đảm coverage cao

Một sealed hierarchy giới hạn các subtype:

~~~java
sealed interface Job permits TextJob, ResizeJob, MoveJob {}
record TextJob(String text) implements Job {}
record ResizeJob(int width, int height) implements Job {}
record MoveJob(Point target) implements Job {}
~~~

Switch với đủ ba nhóm subtype có thể được compiler coi là **exhaustive** mà không cần `default`:

~~~java
static String kind(Job job) {
    return switch (job) {
        case null -> "NULL";
        case TextJob(var text) -> "TEXT";
        case ResizeJob(var w, var h) -> "RESIZE";
        case MoveJob(var target) -> "MOVE";
    };
}
~~~

**Exhaustiveness** là kết luận lúc biên dịch: tập case đủ bao trùm kiểu selector được phép. **Coverage** là kết quả sau khi chạy test: các đường điều khiển đã được thực thi đến đâu. Một switch exhaustive nhưng test chỉ gọi `kind(new TextJob("Hi"))` vẫn chưa kiểm tra hành vi của `ResizeJob`, `MoveJob`, `null`.

Một số nhánh dự phòng do compiler tạo có thể phục vụ những tình huống tương thích nhị phân bất thường (như sealed hierarchy thay đổi sau khi biên dịch). Không nên viết test thiếu ý nghĩa chỉ để “đụng” một nhánh bytecode bất thường hoặc làm sai mô hình domain.

JaCoCo **0.8.11** là bản chính thức hỗ trợ Java 21 và có bộ lọc cho một phần bytecode do compiler tạo cho **record patterns** và **exhaustive switch expressions**. Khi làm việc với Java 21+, sử dụng bản JaCoCo hỗ trợ phiên bản Java đang chạy và đọc release notes, bởi bộ lọc compiler-generated code có thể thay đổi tỷ lệ/điểm hiển thị giữa các phiên bản.

## 8. Chương trình hoàn chỉnh Java 21+ với ma trận 10 kịch bản

Tạo tệp **`PatternBranchCoverageDemo.java`**:

~~~java
public class PatternBranchCoverageDemo {
    sealed interface Job permits TextJob, ResizeJob, MoveJob {}

    record TextJob(String text) implements Job {}
    record ResizeJob(int width, int height) implements Job {}
    record Point(int x, int y) {}
    record MoveJob(Point target) implements Job {}

    static String route(Job job) {
        return switch (job) {
            case null -> "NULL";

            case TextJob(var text)
                    when text == null || text.isBlank() ->
                "EMPTY_TEXT";

            case TextJob(var text) ->
                "TEXT:" + text;

            case ResizeJob(var w, var h)
                    when w <= 0 || h <= 0 ->
                "INVALID_SIZE";

            case ResizeJob(var w, var h) ->
                "AREA:" + (w * h);

            case MoveJob(Point(var x, var y))
                    when x == y ->
                "DIAGONAL:" + x;

            case MoveJob(Point(var x, var y)) ->
                "MOVE:" + x + "," + y;

            case MoveJob(var target) ->
                "NO_TARGET";
        };
    }

    static void check(String name, String expected, Job value) {
        String actual = route(value);
        if (!expected.equals(actual)) {
            throw new AssertionError(name + ": expected "
                    + expected + " but got " + actual);
        }
        System.out.println(name + " -> " + actual);
    }

    public static void main(String[] args) {
        check("null", "NULL", null);
        check("text-null", "EMPTY_TEXT", new TextJob(null));
        check("text-blank", "EMPTY_TEXT", new TextJob("   "));
        check("text-valid", "TEXT:Java", new TextJob("Java"));
        check("size-width", "INVALID_SIZE", new ResizeJob(0, 7));
        check("size-height", "INVALID_SIZE", new ResizeJob(4, 0));
        check("size-valid", "AREA:12", new ResizeJob(4, 3));
        check("move-diagonal", "DIAGONAL:2",
                new MoveJob(new Point(2, 2)));
        check("move-regular", "MOVE:2,5",
                new MoveJob(new Point(2, 5)));
        check("move-no-target", "NO_TARGET", new MoveJob(null));
    }
}
~~~

Biên dịch và chạy bằng **JDK 21 trở lên**:

~~~bash
javac --release 21 PatternBranchCoverageDemo.java
java PatternBranchCoverageDemo
~~~

Đầu ra kỳ vọng:

~~~text
null -> NULL
text-null -> EMPTY_TEXT
text-blank -> EMPTY_TEXT
text-valid -> TEXT:Java
size-width -> INVALID_SIZE
size-height -> INVALID_SIZE
size-valid -> AREA:12
move-diagonal -> DIAGONAL:2
move-regular -> MOVE:2,5
move-no-target -> NO_TARGET
~~~

Chương trình sử dụng `main` làm **harness kiểm tra hành vi**: mỗi ca xác nhận chính xác kết quả hoặc ném `AssertionError` nếu sai. Chạy file bằng lệnh `java` chỉ kiểm chứng kết quả chương trình; **nó không tự sinh báo cáo JaCoCo**. Muốn đo C1, chương trình phải được chạy trong một phiên có agent/instrumentation JaCoCo hoặc qua quy trình build/test đã cấu hình agent.

## 9. Test matrix: từ tên case đến bằng chứng về đường đi

| ID test | Input | Kết quả | Đường đi quan trọng |
| --- | --- | --- | --- |
| T1 | `null` | `NULL` | Selector null |
| T2 | `TextJob(null)` | `EMPTY_TEXT` | Text pattern match, vế trái của `||` true |
| T3 | `TextJob("   ")` | `EMPTY_TEXT` | Vế trái false, `isBlank()` true |
| T4 | `TextJob("Java")` | `TEXT:Java` | Guard String false, đi nhánh thường |
| T5 | `ResizeJob(0, 7)` | `INVALID_SIZE` | `w <= 0` true, vế sau short-circuit |
| T6 | `ResizeJob(4, 0)` | `INVALID_SIZE` | `w <= 0` false, `h <= 0` true |
| T7 | `ResizeJob(4, 3)` | `AREA:12` | Guard Resize false, đi nhánh thường |
| T8 | `MoveJob(Point(2,2))` | `DIAGONAL:2` | Nested Point match, guard true |
| T9 | `MoveJob(Point(2,5))` | `MOVE:2,5` | Nested Point match, guard false |
| T10 | `MoveJob(null)` | `NO_TARGET` | Nested Point fail vì component null, fallback Move |

Ma trận này giúp giải thích **vì sao** một nhánh nghiệp vụ đã được kiểm tra, thay vì chỉ viện dẫn một tỷ lệ tổng. Bạn có thể thêm ca khác nếu có điều kiện nghiệp vụ như số âm, số lớn gây tràn `int`, username dài, locale, exception hoặc object thay đổi theo thời gian.

**Nhận xét quan trọng:** T2 và T3 đi vào cùng một nhánh trả về `EMPTY_TEXT`, nhưng chúng khác nhau về quyết định ngắn mạch. Chỉ kiểm tra “đầu ra của mỗi case” sẽ bỏ lỡ sự khác biệt này; đây là lý do **case-label coverage** và **branch/condition coverage** không phải một thứ.

## 10. Đưa ma trận vào JUnit 5 để JaCoCo thu thập coverage

Trong project Maven, thường đặt mã chính tại `src/main/java/PatternBranchCoverageDemo.java` và mã test tại `src/test/java/PatternBranchCoverageTest.java` (ví dụ tối giản dùng default package; project thực tế nên đặt package nhất quán).

Một test JUnit 5 dùng `@ParameterizedTest` + `@MethodSource`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.params.provider.Arguments.arguments;

import java.util.stream.Stream;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;

class PatternBranchCoverageTest {
    @ParameterizedTest(name = "{0}")
    @MethodSource("cases")
    void routeCases(String id,
                    PatternBranchCoverageDemo.Job input,
                    String expected) {
        assertEquals(expected, PatternBranchCoverageDemo.route(input));
    }

    static Stream<Arguments> cases() {
        return Stream.of(
            arguments("null", null, "NULL"),
            arguments("text-null",
                new PatternBranchCoverageDemo.TextJob(null),
                "EMPTY_TEXT"),
            arguments("text-blank",
                new PatternBranchCoverageDemo.TextJob("   "),
                "EMPTY_TEXT"),
            arguments("text-valid",
                new PatternBranchCoverageDemo.TextJob("Java"),
                "TEXT:Java"),
            arguments("size-width",
                new PatternBranchCoverageDemo.ResizeJob(0, 7),
                "INVALID_SIZE"),
            arguments("size-height",
                new PatternBranchCoverageDemo.ResizeJob(4, 0),
                "INVALID_SIZE"),
            arguments("size-valid",
                new PatternBranchCoverageDemo.ResizeJob(4, 3),
                "AREA:12"),
            arguments("move-diagonal",
                new PatternBranchCoverageDemo.MoveJob(
                    new PatternBranchCoverageDemo.Point(2, 2)),
                "DIAGONAL:2"),
            arguments("move-regular",
                new PatternBranchCoverageDemo.MoveJob(
                    new PatternBranchCoverageDemo.Point(2, 5)),
                "MOVE:2,5"),
            arguments("move-no-target",
                new PatternBranchCoverageDemo.MoveJob(null),
                "NO_TARGET")
        );
    }
}
~~~

Mỗi dòng trong `cases()` thành một lần chạy test với input và expected độc lập. Test này khẳng định **kết quả đúng**; coverage công cụ ghi nhận những đường bytecode thực sự đi qua. Một test có assertion **không** tự chứng minh đầy đủ các trường hợp input chưa được liệt kê.

Lưu ý: câu lệnh `assertEquals` ở đây kiểm tra kết quả method `route`; nếu muốn đo chính xác code sản phẩm, hãy xem báo cáo ở **`PatternBranchCoverageDemo.route`**, không lấy tỷ lệ chung cả project (vốn còn chứa mã test/harness/utility) làm thay thế.

## 11. Cấu hình JaCoCo Maven và mở báo cáo

Ví dụ plugin cho dự án Maven có JUnit 5, phù hợp Java 21. Trong `pom.xml`, đặt dependency JUnit 5 ở `<dependencies>` và plugins ở `<build><plugins>`. Cấu hình tối giản:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>

<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
        </plugin>

        <plugin>
            <groupId>org.jacoco</groupId>
            <artifactId>jacoco-maven-plugin</artifactId>
            <version>0.8.16</version>
            <executions>
                <execution>
                    <goals>
                        <goal>prepare-agent</goal>
                    </goals>
                </execution>
                <execution>
                    <id>coverage-report</id>
                    <phase>verify</phase>
                    <goals>
                        <goal>report</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

Đây là **đoạn cấu hình bên trong** một `pom.xml` hợp lệ, không phải file POM độc lập vì thiếu phần tử `<project>`, tọa độ Maven của project và các khai báo khác.

Nếu project đã có cấu hình compiler/Surefire/JUnit, hãy **hợp nhất** những phần cần thiết thay vì thêm trùng plugin. Chỉ khi dùng JaCoCo agent trong JVM chạy JUnit mới có kết quả đo phù hợp.

Chạy:

~~~bash
mvn clean verify
~~~

Với build thành công, mục tiêu `prepare-agent` kích hoạt instrument khi Surefire chạy unit test và mục tiêu `report` trong phase `verify` tạo báo cáo, thường ở:

~~~text
target/site/jacoco/index.html
target/site/jacoco/jacoco.xml
target/site/jacoco/jacoco.csv
~~~

Đường dẫn có thể đổi nếu project cấu hình output khác hoặc là multi-module. Mở `index.html`, chọn package chứa `PatternBranchCoverageDemo`, chọn class rồi nhấp method `route` để kiểm tra C1/diamond.

**Không coi con số coverage cụ thể là kết quả bài này:** chương trình `main` đã được chạy để kiểm tra đầu ra; các bước trên hướng dẫn **bạn tự chạy JaCoCo trong Maven** và đọc report của chính JDK/compiler/build/test suite. Các bộ lọc bytecode và code phát sinh có thể làm kết quả khác nhau theo JaCoCo/JDK.

## 12. Khi thấy màu vàng ở dòng pattern, bổ sung test thế nào?

Giả sử báo cáo vẫn hiện partial branch coverage ở vùng `TextJob`:

~~~java
case TextJob(var text)
        when text == null || text.isBlank() ->
    "EMPTY_TEXT";
case TextJob(var text) ->
    "TEXT:" + text;
~~~

**Cách suy luận đúng:**

1. Kiểm tra test đã có **TextJob** và **không phải TextJob** hay chưa. Nếu chỉ test String input ở một switch trên `Object`, các pattern subtype khác có thể chưa xuất hiện.
2. Có `TextJob(null)` chưa? Trường hợp này kiểm tra vế trái `text == null` true.
3. Có `TextJob("  ")` chưa? Trường hợp này khiến vế trái false, vế phải `isBlank()` true.
4. Có `TextJob("ok")` chưa? Trường hợp này khiến guard false và chọn case TextJob thường.
5. Có một **null selector** (khác TextJob chứa null component) chưa?
6. Chạy lại report và xem nhánh còn missed. Không tự suy luận từ màu mà không kiểm tra được **branch nào đã tăng**.

Với `MoveJob`, nếu chỉ có test `Point(2,2)` (guard true), thêm `Point(2,5)` để tạo guard false; thêm `MoveJob(null)` để kiểm tra nested pattern fail vì component null.

Nếu sau những test này vẫn có missed branch, hãy xem các điểm quyết định ở **bytecode/report** và cân nhắc code sinh của compiler hoặc đường đi khác. Tránh thêm một test “vô nghĩa” chỉ để đẩy tỷ lệ; test phải tương ứng với hành vi có thể xảy ra hoặc một hợp đồng kỹ thuật cần bảo vệ.

## 13. Những điểm dễ đọc sai trong coverage report

### 13.1. 100% C1 không đồng nghĩa mọi input đúng

Branch coverage chỉ cho biết các nhánh được instrument đã chạy, **không** cho biết assertion có đủ mạnh, test có kiểm tra kết quả sai hay không, hay data edge cases có được phủ hết.

Ví dụ, với điều kiện `width > 0`, thử `width = 1` và `width = 0` có thể đi qua hai nhánh, nhưng không tự kiểm tra overflow `width * height`. Muốn kiểm tra logic đúng, cần boundary-value tests, property-based tests hoặc mutation testing khi phù hợp.

### 13.2. Báo cáo C1 không phải MC/DC

Bốn trường hợp true/false của một biểu thức Boolean phức hợp có thể quan trọng theo tiêu chuẩn kiểm thử **MC/DC** (mỗi điều kiện con chứng minh ảnh hưởng độc lập tới quyết định). JaCoCo C1 **không** trực tiếp báo tỷ lệ MC/DC.

Với `w <= 0 || h <= 0`, một bộ test cố gắng chứng minh sự ảnh hưởng độc lập của hai điều kiện sẽ cần các đầu vào phù hợp, ví dụ `(0,3)`, `(4,0)` và `(4,3)`; các báo cáo vẫn cần đọc theo định nghĩa metric bạn thực sự dùng.

### 13.3. Không giả định một case = một branch

Các phép type test, nested record deconstruction, guard và switch dispatch có thể tạo ra nhiều nhánh bytecode. Một số nhánh compiler-generated cũng có thể được JaCoCo **lọc khỏi report**. Do đó không nên tính `đã test 7 case / 8 case = 87,5% C1` rồi ghi thành số liệu JaCoCo.

**Thực tế nên lưu hai kết quả khác nhau:** số ca/kịch bản nghiệp vụ được test (từ ma trận) và C1 đo được (từ report). Chúng bổ sung cho nhau chứ không thay thế nhau.

### 13.4. Exception paths không nằm trong bộ đếm branch C1

JaCoCo không tính exception handling như các nhánh C1. Test vẫn nên có ca ném exception khi dữ liệu không hợp lệ, ví dụ record constructor cấm null, command handler từ chối trạng thái không hợp lệ hay parser gặp dữ liệu sai.

Không cố “đạt 100% C1” bằng cách bỏ test exception; **C1 và độ hoàn chỉnh hành vi là hai khái niệm khác nhau**.

### 13.5. Source layout và compiler bytecode ảnh hưởng cách hiển thị

Một số quyết định có thể nằm trên cùng một dòng source, ví dụ:

~~~java
case TextJob(var t) when t == null || t.isBlank() -> "EMPTY_TEXT";
~~~

JaCoCo mapping của bytecode đến dòng source có thể đặt nhiều nhánh trên một dòng/hình thoi. Tách điều kiện dài thành các dòng dễ đọc có thể giúp review, nhưng không làm thay đổi tự động hành vi hay số nhánh thực sự của cùng logic. Quan trọng là đọc metric của method và đối chiếu với test matrix.

### 13.6. JaCoCo version và generated code

JaCoCo 0.8.11 chính thức hỗ trợ Java 21 và bổ sung bộ lọc một số đoạn bytecode do compiler sinh cho record patterns và exhaustive switch expressions. Các bản mới hơn có thể thay đổi khả năng hỗ trợ JDK hoặc filtering. Tránh so sánh máy móc các phần trăm của hai build chạy công cụ khác phiên bản hoặc compiler/JDK khác nhau mà không ghi nhận điều kiện đo.

## 14. Quy trình đánh giá coverage theo nhánh pattern

Một cách làm có thể áp dụng khi review pull request:

1. **Đọc cấu trúc pattern switch:** ghi lại từng type/record pattern, guard và nhánh tổng quát hoặc `case null`.
2. **Vẽ test matrix:** mỗi nhóm input phải có ví dụ về pattern match, guard true/false và trường hợp nested pattern không khớp khi có ý nghĩa.
3. **Viết test có assertion:** không chỉ gọi method. Trên mỗi đường đi, kiểm tra giá trị trả về hoặc exception hợp đồng.
4. **Chạy build/test với JaCoCo phù hợp JDK:** bảo đảm agent chạy trong JVM thực thi test.
5. **Đọc coverage ở phạm vi method:** xem `Missed Branches`, không chỉ nhìn tổng % module.
6. **Đối chiếu coverage với matrix:** xác định trường hợp chưa chạy và chất lượng assertion của ca đã chạy.
7. **Phân loại gap:** đường nghiệp vụ cần test, guard/short-circuit chưa test, lỗi exception cần test riêng, hay compiler-generated/report artifact.
8. **Bổ sung kiểm thử có ý nghĩa**, chạy lại và chỉ chốt khi cả hành vi và mức độ bao phủ đáp ứng tiêu chí dự án.

Có thể dùng một bảng review đơn giản:

| Nhóm input | Test đã có? | Assertion đủ mạnh? | Branch report có gap? | Hành động |
| --- | --- | --- | --- | --- |
| Null selector | Có/Không | Có/Không | Có/Không | Bổ sung xử lý/test null |
| Type pattern match | Có/Không | Có/Không | Có/Không | Kiểm tra output nhánh đúng |
| Guard true | Có/Không | Có/Không | Có/Không | Thêm ca guard đúng |
| Guard false | Có/Không | Có/Không | Có/Không | Thêm ca chuyển sang case tiếp |
| Nested record component null | Có/Không | Có/Không | Có/Không | Thêm ca nested no-match |
| Error path/exception | Có/Không | Có/Không | Không phản ánh đầy đủ ở C1 | Assert exception riêng |

## 15. Bài tập luyện đọc coverage

**Bài 1.** Cho method có hai nhánh `case String s when s.isBlank()` và `case String s`. Hai test `"   "` và `"Java"` chứng minh những đường đi gì? Có cần test `null` hoặc kiểu khác không nếu method nhận `Object`?

**Bài 2.** Với guard `w <= 0 || h <= 0`, tại sao chỉ test `(0,5)` và `(3,2)` chưa chứng minh được đường vế phải true? Hãy bổ sung một input.

**Bài 3.** Với `MoveJob(Point(var x,var y)) when x == y`, `MoveJob(Point(var x,var y))` và `MoveJob(var target)`, hãy dự đoán nhánh được chọn cho ba giá trị: `Point(1,1)`, `Point(1,3)` và component `target = null`.

**Bài 4.** Báo cáo JaCoCo cho một method hiển thị 17 covered branches và 20 total branches. Tỷ lệ C1 là bao nhiêu? Vì sao không nên suy ra số nhãn `case` từ hai con số này?

**Bài 5.** Một switch exhaustive trên sealed interface có 100% C1 nhưng test chưa kiểm tra constructor command ném `IllegalArgumentException` khi số lượng âm. Mức độ hoàn chỉnh của test suite đã đủ chưa? Vì sao?

**Đáp án:**

- Bài 1: `"   "` kiểm tra guard true; `"Java"` kiểm tra guard false và String branch thường. Với selector kiểu Object, cần xem thêm `case null` và nhánh kiểu khác theo hợp đồng method.
- Bài 2: cần `(3,0)`: vế trái false, vế phải true. `(3,2)` kiểm tra cả hai false.
- Bài 3: lần lượt nhánh **DIAGONAL**, nhánh **MOVE** và nhánh **NO_TARGET**.
- Bài 4: **85%**; đó là số nhánh bytecode được JaCoCo đếm, không phải nhãn source case.
- Bài 5: **chưa thể kết luận đã đủ**; exception path không được tính trong C1 theo định nghĩa JaCoCo và vẫn cần assertion riêng để xác nhận hợp đồng dữ liệu.

## 16. Tổng kết

Để **đọc coverage theo nhánh pattern** đúng trong Java 21:

- Dùng **JaCoCo Branches (C1)** để biết nhánh bytecode của `if`/`switch` đã được chạy đến đâu, nhưng **không** quy đổi trực tiếp số `case` thành C1.
- Với `when`, kiểm tra **guard true và false**; với `&&`/`||`, xem từng đường ngắn mạch có ý nghĩa.
- Với **record patterns lồng**, kiểm tra component khớp, không khớp và null component; với switch trên reference, xét selector null.
- Với **sealed hierarchy**, nhớ **exhaustiveness là compile-time**, còn coverage là **runtime**.
- Dùng **test matrix + assertions + JaCoCo report** cùng nhau. Tỷ lệ phần trăm cao là tín hiệu, không phải bằng chứng chương trình đúng trên mọi input.

### Tài liệu tham khảo

- [JaCoCo — Coverage Counters](https://www.jacoco.org/jacoco/trunk/doc/counters.html): định nghĩa Instructions, Branches, Lines, Complexity và ý nghĩa hình thoi.
- [JaCoCo — Change History](https://www.jacoco.org/jacoco/trunk/doc/changes.html): hỗ trợ Java 21 từ 0.8.11 và lọc phần bytecode tạo từ record patterns/exhaustive switch.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): type patterns, guard `when`, null và exhaustiveness.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): nested deconstruction và component matching.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): cú pháp case pattern, dominance, null và exhaustive switch.
