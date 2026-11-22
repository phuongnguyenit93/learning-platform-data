# includes, excludes, tag hoặc nhóm kiểm thử theo framework trong Maven

Trong một dự án Java, có thể có hàng trăm test: test chạy nhanh khi sửa code, test kiểm tra trường hợp biên, test chậm, test cần database và test tích hợp. Nếu chạy tất cả trong mỗi lần `mvn test`, vòng phản hồi có thể quá lâu. Nhưng nếu loại test bằng cách đổi tên file hoặc thêm `@Disabled` hàng loạt, rất dễ che mất lỗi.

**Maven Surefire Plugin** cho phép chọn test theo **tên lớp hoặc đường dẫn lớp** bằng `includes`, `excludes` và `-Dtest`. Còn **JUnit Jupiter (JUnit 5), JUnit 4 và TestNG** cho phép gắn nhãn **tag/category/group** cho test rồi lọc bằng `groups` và `excludedGroups`. Đây là **hai tầng chọn lọc khác nhau**, đôi khi phối hợp trong cùng một build:

1. **Tầng Maven/Surefire:** quyết định những lớp test nào nằm trong phạm vi quét/chạy.
2. **Tầng framework/provider:** quyết định những test/method có tag, category hoặc group nào sẽ được thực thi trong các lớp đã chọn.

Một lớp bị loại bởi `excludes` thường không được đưa tới framework để khám phá test; thêm `@Tag("fast")` vào lớp đó không tự cứu nó khỏi `excludes`. Ngược lại, một lớp trùng mẫu `includes` nhưng mọi method đều bị filter tag loại thì có thể không còn method nào chạy.

Bài này dùng Maven 3.9.x, Java 17+, Maven Surefire Plugin 3.5.2, Maven Failsafe Plugin 3.5.2 và JUnit Jupiter 5.11.0 trong ví dụ chính. Đối với phiên bản Surefire 3.6.0 trở lên, Apache Maven đã thống nhất execution qua JUnit Platform; vì vậy luôn đọc tài liệu theo **đúng plugin version đang dùng** khi kết hợp nhiều framework.

## 1. Phân biệt class pattern, tag và group

| Cơ chế | Công cụ quyết định | Đơn vị chính | Ví dụ | Phạm vi |
| --- | --- | --- | --- | --- |
| `<includes>` | Surefire/Failsafe | Tên lớp test sau khi compile | `**/*Test.java` | Chọn lớp được quét |
| `<excludes>` | Surefire/Failsafe | Tên lớp test sau khi compile | `**/*ExperimentalTest.java` | Loại lớp khỏi tập quét |
| `-Dtest=...` | Surefire | Lớp hoặc method cụ thể | `-Dtest=PriceFastTest` | Chọn test để chạy trong một invocation |
| JUnit 5 `@Tag` | JUnit Platform/Jupiter | Lớp hoặc method | `@Tag("fast")` | Metadata; tự nó không bỏ qua test |
| JUnit 4 `@Category` | JUnit 4/Vintage provider | Lớp hoặc method | `@Category(Fast.class)` | Category kiểu class/interface |
| TestNG `groups` | TestNG | Method hoặc class | `@Test(groups="smoke")` | Group của framework |
| Surefire `groups` | Surefire chuyển cho provider | Tag/category/group | `<groups>fast</groups>` | Giữ các test có nhãn phù hợp |
| Surefire `excludedGroups` | Surefire chuyển cho provider | Tag/category/group | `<excludedGroups>slow</excludedGroups>` | Loại các test có nhãn phù hợp |

**Đừng đồng nhất `<include>` với `@Tag`.** `<include>**/*FastTest.java</include>` xét **tên lớp**; `@Tag("fast")` xét metadata framework. Một class tên `ShippingTest` vẫn có thể được chạy trong nhóm `fast` nếu được gắn `@Tag("fast")`.

Cũng không đồng nhất **Maven profiles** (`-Psmoke`) với **test tags** (`-Dgroups=smoke`). Profile là cách kích hoạt một tập cấu hình POM; tag là thuộc tính của test trong framework. Có thể dùng profile để gán `<groups>smoke</groups>`, nhưng hai cơ chế không tự động giống nhau.

## 2. Surefire và Failsafe: dùng plugin nào?

### 2.1. Maven Surefire cho unit tests

Với dự án `packaging=jar`, goal `surefire:test` thường được lifecycle gọi ở phase `test`. Các file Java test nằm trong `src/test/java` được biên dịch vào `target/test-classes` trước khi Surefire khám phá test.

```text
src/test/java
  |
  +-- maven-compiler-plugin:testCompile
          |
          v
target/test-classes
  |
  +-- maven-surefire-plugin:test
          |
          +-- includes / excludes / -Dtest  (lọc lớp)
          |
          +-- JUnit/TestNG provider          (lọc tag/group, chạy method)
          |
          v
target/surefire-reports
```

Mẫu `**/*Test.java` là cách viết trong cấu hình Surefire, nhưng quá trình quét thực tế làm việc với **class files đã compile**, không đơn giản chạy `javac` cho từng tên file một cách độc lập.

### 2.2. Maven Failsafe cho integration tests

Maven Failsafe Plugin thường thực thi goals `integration-test` và `verify` trong lifecycle tương ứng. Các tên mặc định của Failsafe hướng tới lớp integration test:

- `**/IT*.java`
- `**/*IT.java`
- `**/*ITCase.java`

Nên dùng `mvn verify` để chạy đúng cả `failsafe:integration-test` và `failsafe:verify`. **Đừng dừng ở `mvn integration-test` rồi kết luận integration tests đạt**, vì Failsafe có cơ chế trì hoãn báo lỗi test đến goal `verify` để cho giai đoạn hậu xử lý/teardown hoàn tất.

Surefire và Failsafe có bộ `includes/excludes/groups/excludedGroups` riêng; chúng không tự chia tập test đúng chỉ vì có tên plugin trong POM. Thiết kế quy ước tên rõ ràng: `*Test.java` cho unit và `*IT.java` cho integration, sau đó kiểm tra reports.

## 3. Các includes mặc định của Maven Surefire

Theo tài liệu Apache Maven Surefire, nếu **không cấu hình includes tùy chỉnh**, mặc định plugin nhận những tên lớp theo mẫu:

| Pattern | Ví dụ phù hợp |
| --- | --- |
| `**/Test*.java` | `TestPrice.java` |
| `**/*Test.java` | `PriceTest.java` |
| `**/*Tests.java` | `PriceTests.java` |
| `**/*TestCase.java` | `PriceTestCase.java` |

Chữ `**/` bao phủ package/subdirectory. Mẫu `*` là wildcard (không phải regex). Ví dụ `PriceSpec.java` **không tự khớp** bốn mẫu mặc định, trừ khi plugin được cấu hình thêm include.

Chú ý:

- Tên lớp test có thể được chọn nhưng **framework vẫn cần test engine/provider phù hợp** và method test hợp lệ.
- Surefire mặc định loại **nested classes**, trong khi JUnit Jupiter có cách khám phá `@Nested` qua lớp ngoài. Không giả định tất cả inner classes được chọn như top-level test classes.
- Các file `src/test/java` không được biên dịch thành lớp hợp lệ thì build có thể fail từ `testCompile` trước khi tới phần lọc Surefire.
- `mvn test` cũng phải resolve được Surefire plugin, JUnit/TestNG dependencies và những build plugins liên quan.

### 3.1. Tự đặt includes

Ví dụ **đoạn cấu hình Surefire** (đặt trong `<build><plugins>` của POM):

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <includes>
            <include>**/*Test.java</include>
            <include>**/*Tests.java</include>
        </includes>
    </configuration>
</plugin>
```

Khi khai báo includes, bạn đang chủ động kiểm soát danh sách mẫu **thay vì đơn thuần dựa vào tất cả mẫu mặc định**. Một class `TestPrice.java` khớp mặc định nhưng không khớp hai mẫu tùy chỉnh bên trên có thể không được chọn. Đây là bẫy phổ biến khi đội thêm một include mới nhưng vô tình làm biến mất các lớp test đang theo quy ước cũ.

**Khuyến nghị:** đặt tên test nhất quán và chỉ tự cấu hình includes nếu thực sự cần. Kiểm tra số test trong reports trước/sau thay đổi.

## 4. excludes: loại tên lớp, không phải xóa hoặc disable test

`<excludes>` chỉ ra các lớp cần loại khỏi tập quét:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.5.2</version>
    <configuration>
        <includes>
            <include>**/*Test.java</include>
        </includes>
        <excludes>
            <exclude>**/*ExperimentalTest.java</exclude>
            <exclude>**/*IntegrationTest.java</exclude>
        </excludes>
    </configuration>
</plugin>
```

Với cấu hình này:

- `InvoiceFastTest.java` có thể được Surefire chọn.
- `InvoiceExperimentalTest.java` khớp includes nhưng **bị excludes loại**.
- `InvoiceIntegrationTest.java` cũng bị loại vì suffix `IntegrationTest`.
- `InvoiceIT.java` không khớp includes nên cũng không vào tập Surefire này (có thể dành cho Failsafe).

Đây là **pattern file/class name**, không phải đường dẫn tương đối từ `src/test/java` khi chạy chương trình Java. Dấu slash trong biểu thức classpath/pattern nên dùng `/` trên cả Windows nếu viết dạng path, theo tài liệu Surefire.

**Không dùng excludes để che mã test bị hỏng kéo dài.** Nếu test cần tài nguyên ngoài hoặc chỉ chạy trong CI, hãy quyết định nó thuộc integration-test hay unit-test, dùng tags/groups và quản lý môi trường phù hợp. Mọi trường hợp exclude có chủ đích nên có lý do và test coverage thay thế.

### 4.1. Excludes không phải @Disabled

JUnit Jupiter `@Disabled`/JUnit 4 `@Ignore` đánh dấu test bị bỏ qua theo cơ chế framework. `@Tag("slow")` **không bỏ qua test**; nó chỉ là nhãn, cần filter để quyết định thực thi. `<excludes>` có thể khiến class không được khám phá ngay từ tầng Surefire; báo cáo số test/skipped sẽ khác với `@Disabled`.

Đừng lấy “Maven BUILD SUCCESS” làm chứng cứ test đã chạy. Hãy kiểm tra `Tests run`, reports và bộ test cụ thể.

### 4.2. Nhiều mẫu, phủ định và regex

Surefire còn hỗ trợ syntax mở rộng, ví dụ:

```xml
<includes>
    <include>**/*Test.java</include>
    <include>%regex[.*Fast.*.class]</include>
</includes>
```

Đây là **đoạn cấu hình minh họa**, không cần dùng khi chỉ có suffix thông thường. Với `%regex[...]`, regex áp dụng theo tên class file/path; dấu `.class` được hiểu theo quy tắc đặc thù của Surefire regex, không nhất thiết giống regex path bạn chạy với `grep`. Surefire cũng hỗ trợ dạng danh sách nhiều pattern và ký hiệu `!` trong một số tham số include/test, nhưng `excludes` không sử dụng phủ định `!` theo cùng cách.

**Đừng đổi wildcard `**/` thành regex hoặc cố dùng cú pháp phủ định trong `<exclude>` mà chưa xem tài liệu plugin.** Với project bình thường, các mẫu suffix `**/*Test.java` và `**/*IT.java` dễ hiểu hơn.

## 5. Lọc một lớp hoặc method từ command line với -Dtest

Khi đang debug, bạn thường không muốn sửa POM mỗi lần:

```bash
# Chạy đúng một lớp
mvn -Dtest=InvoiceFastTest test

# Chạy một method của lớp đó (khi provider/version hỗ trợ)
mvn -Dtest=InvoiceFastTest#addsAmounts test

# Chọn theo wildcard trong tên lớp
mvn -Dtest=Invoice*Test test

# Chọn nhiều lớp
mvn -Dtest=InvoiceFastTest,InvoiceEdgeTest test
```

Tùy shell, các ký tự `*`, `#` hoặc `,` có thể cần quote để truyền nguyên vẹn tới Maven, ví dụ `-Dtest="InvoiceFastTest#addsAmounts"`.

**`-Dtest` không phải một Maven profile.** Nó là **user property của Surefire**, dùng để chọn test trong lượt chạy. Theo Surefire, việc chỉ định `test` có thể **override các thiết lập include/exclude theo lớp** thông thường. Vì vậy một class đã bị `<excludes>` loại trong build mặc định có thể vẫn được chạy khi bạn chủ động `-Dtest=...`. Không dùng `excludes` như cơ chế bảo mật hoặc cấm thực thi.

Còn một điểm cần nhớ: `-Dtest` chọn class/method, nhưng provider vẫn có thể áp dụng bộ lọc framework khác, chẳng hạn JUnit 5 tags. Nếu build dùng `-Dgroups=fast` đồng thời chọn một test chỉ có `@Tag("slow")`, có thể không có test nào được chạy hoặc có lỗi tùy phiên bản/cấu hình.

### 5.1. Khi không có lớp phù hợp

Ví dụ:

```bash
mvn -Dtest=NonExistingTest test
```

Surefire thường báo **không có test được chọn theo `-Dtest`** và có thể fail theo tham số `failIfNoSpecifiedTests`. Đây là cơ chế an toàn: typo trong CI không nên biến pipeline thành “test pass” giả.

Tách hai cấu hình:

- `failIfNoTests`: xử lý khi không có test phù hợp với quá trình chạy thông thường.
- `failIfNoSpecifiedTests`: xử lý trường hợp người dùng **chỉ định test bằng `-Dtest`** nhưng không match.

Có thể tinh chỉnh nếu xây CI reactor nhiều module có module không chứa test đã chọn, nhưng **không nên đặt cả hai thành false ở mọi project** chỉ để tránh lỗi đỏ.

## 6. JUnit Jupiter: dùng @Tag và groups/excludedGroups

JUnit Jupiter (thường được gọi là JUnit 5) cho phép gắn tag ở class hoặc method:

```java
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

@Tag("fast")
class InvoiceFastTest {
    @Test
    void addsAmounts() {
        // assertion có nội dung thật trong ví dụ hoàn chỉnh ở mục 9
    }
}
```

Đoạn này **chỉ minh họa annotation**, chưa đủ là một file test độc lập có assertions. Tag tại class được kế thừa bởi các test methods khi framework xác định effective tags; tag tại method dùng cho từng test riêng.

Để **chạy tag** bằng Surefire, dùng tham số `groups`:

```xml
<configuration>
    <groups>fast</groups>
</configuration>
```

Để **loại tag**, dùng `excludedGroups`:

```xml
<configuration>
    <excludedGroups>slow</excludedGroups>
</configuration>
```

Maven Surefire chuyển chúng cho JUnit Platform provider. Đừng tìm tham số tên `<tags>` của Surefire chỉ vì framework dùng annotation `@Tag`: với JUnit Platform, tên cấu hình được tài liệu là **`groups`** và **`excludedGroups`**.

### 6.1. Tag expressions

JUnit Platform hỗ trợ biểu thức logic để chọn test:

| Biểu thức | Ý nghĩa |
| --- | --- |
| `fast` | Test có tag `fast` |
| `fast | smoke` | Có ít nhất một trong hai tags |
| `fast & !db` | Có `fast` và không có `db` |
| `(smoke | fast) & !integration` | Tag smoke hoặc fast, đồng thời không integration |
| `!slow` | Không có tag slow |

**XML phải escape dấu `&` thành `&amp;`**:

```xml
<configuration>
    <groups>(fast | smoke) &amp; !integration</groups>
    <excludedGroups>db</excludedGroups>
</configuration>
```

Nếu ghi literal `&` trong XML text như `<groups>fast & !db</groups>`, POM **không hợp lệ XML** và Maven fail trước khi chạy tests. Dấu `|` và `!` có thể bị shell diễn giải khi chạy CLI; quote đúng cho Bash/PowerShell/CMD.

Ví dụ chạy qua CLI:

```bash
mvn -Dgroups=fast test
mvn -DexcludedGroups=slow test
mvn -Dgroups="fast | smoke" test
```

Với expression có ký tự `!` trong Bash interactive, nên dùng quote phù hợp để tránh history expansion; với PowerShell và CMD, xem cơ chế quote tương ứng.

### 6.2. Quy ước tag tốt

Nên định nghĩa một tập tag **ít và có ý nghĩa**, chẳng hạn:

- `fast`: đơn vị chạy nhanh, không phụ thuộc external system;
- `slow`: tốn thời gian CPU/I/O trong CI;
- `db`: cần database có chuẩn bị;
- `smoke`: kiểm tra phần quan trọng sau khi build;
- `integration`: kiểm thử qua nhiều component;
- `flaky`: đang được điều tra, **không phải tag để bỏ qua vĩnh viễn**.

Một test có thể có nhiều tag. Hãy phân loại theo **hành vi/phụ thuộc thực tế**, không chỉ đổi annotation để khớp pipeline.

JUnit tags có giới hạn ký tự/tên: không rỗng, không chứa whitespace hoặc các ký tự dành riêng của cú pháp tag expression như `,`, `(`, `)`, `&`, `|`, `!`. Dùng tên đơn giản `fast`, `smoke`, `db` là lựa chọn an toàn.

## 7. JUnit 4 Categories và TestNG Groups khác JUnit 5 Tags

Tên cấu hình Surefire `groups` giống nhau, nhưng **ý nghĩa trong framework khác nhau**.

### 7.1. JUnit 4: @Category dùng class/interface type

JUnit 4.8+ hỗ trợ `@Category`. Ví dụ:

```java
package vn.example.legacy;

import org.junit.Test;
import org.junit.experimental.categories.Category;

interface SlowTests {
}

public class LegacyReportTest {
    @Test
    @Category(SlowTests.class)
    public void runsSlowCheck() {
        org.junit.Assert.assertTrue(true);
    }
}
```

Đây là **đoạn ví dụ JUnit 4 tách biệt**, **không thuộc project JUnit Jupiter hoàn chỉnh ở mục 9**. Nếu chạy trong Maven, cần khai báo dependency JUnit 4 và provider/JUnit Vintage tương ứng (đặc biệt khi trộn với JUnit Jupiter). `SlowTests` là interface được dùng làm category marker.

Ví dụ cấu hình Surefire:

```xml
<configuration>
    <groups>vn.example.legacy.SlowTests</groups>
</configuration>
```

**Không dùng `<groups>slow</groups>` để kỳ vọng nó tự match JUnit 4 marker interface `SlowTests`.** Category của JUnit 4 dựa trên tên type (có thể có quan hệ kế thừa type), khác tag String của JUnit 5.

Với Surefire 3.6.0+, tài liệu Apache Maven xác nhận JUnit 4 chạy qua JUnit Platform Vintage Engine; ở các bản cũ, cơ chế provider khác. Vì thế phải chọn dependency/engine phù hợp khi di chuyển dự án cũ.

### 7.2. TestNG: @Test(groups=...)

TestNG cung cấp group qua annotation:

```java
package vn.example.testng;

import org.testng.Assert;
import org.testng.annotations.Test;

public class ApiSmokeTest {
    @Test(groups = {"smoke", "api"})
    public void checkEndpointContract() {
        Assert.assertEquals(2 + 3, 5);
    }
}
```

Đây là **file ví dụ độc lập khi project có dependency `org.testng:testng`**, không nằm trong project JUnit Jupiter ở mục 9. Lớp vẫn cần được Surefire quét theo class include pattern.

Cấu hình:

```xml
<configuration>
    <groups>smoke,api</groups>
    <excludedGroups>slow</excludedGroups>
</configuration>
```

Đối với TestNG, danh sách group thường viết cách nhau bằng dấu phẩy như trên. TestNG còn hỗ trợ group dependencies, suite XML và các điều kiện framework khác. Khi dùng `suiteXmlFiles`, ý nghĩa tập test được chạy có thể theo file suite và cơ chế provider, không chỉ là glob tên lớp.

**Cảnh báo version:** các release Surefire mới hơn 3.6.0 có cơ chế thống nhất JUnit Platform; dự án TestNG cũ dùng Surefire 3.5.2 hoặc thấp hơn có provider khác. Không sao chép từng cấu hình engine từ một version sang version khác mà không test.

### 7.3. Bảng đối chiếu giữa frameworks

| Framework | Gắn nhãn | Ví dụ nhãn | Surefire filter |
| --- | --- | --- | --- |
| JUnit Jupiter | `@Tag("fast")` | String `fast` | `groups=fast` |
| JUnit 4 | `@Category(Fast.class)` | Marker type `vn.example.Fast` | `groups=vn.example.Fast` |
| TestNG | `@Test(groups={"fast"})` | String `fast` | `groups=fast` |

Khi dự án có cả JUnit 4, Jupiter và TestNG, cùng một `groups` chưa chắc lọc đồng nhất nếu provider/engine xử lý khác nhau. Nên thiết kế pipeline thống nhất bằng framework chủ đạo hoặc test riêng từng engine, và xác minh reports.

## 8. Lưu ý về thứ tự lọc và các cấu hình tương tác

Hãy nghĩ theo **ba câu hỏi**:

1. **Lớp này có nằm trong tập Surefire/Failsafe quét không?** Xem includes/excludes/test naming và `-Dtest`.
2. **Provider có chạy được framework này không?** Xem JUnit Jupiter engine, JUnit Vintage, TestNG version/dependencies.
3. **Method/class có qua bộ lọc tag/group không?** Xem `groups`, `excludedGroups`, annotations và framework discovery.

Ví dụ:

| Class | Tên class hợp `**/*Test.java`? | JUnit tag | Kết quả với groups=fast |
| --- | --- | --- | --- |
| `AmountFastTest` | Có | fast | Được chọn |
| `AmountSlowTest` | Có | slow | Bị loại bởi tag filter |
| `AmountEdgeTest` | Có | edge | Bị loại bởi tag filter |
| `AmountExperimentalTest` | Có, nhưng exclude `*ExperimentalTest.java` | fast | **Không tới provider**, trừ khi thay đổi selection bằng cách có chủ đích |
| `AmountIT` | Không | fast | Không phải Surefire class trong cấu hình này |

Đó là lý do “thêm `@Tag("fast")` cho `AmountIT`” không tự làm Surefire chạy nó trong unit-test phase; tên lớp vẫn nằm ngoài includes. Ngược lại, nếu đổi tên `AmountIT` thành `AmountFastTest`, nó có thể lọt vào unit suite dù vốn cần container/database, nên cần **kỷ luật tên + tag**.

### 8.1. Parameter CLI có thể ảnh hưởng tới các goals khác

`mvn -Dgroups=smoke verify` sử dụng **user property** cho một Maven invocation. Nếu project cấu hình cả Surefire và Failsafe với các tham số cùng tên, property có thể ảnh hưởng đến **cả hai goals**, tùy plugin config/precedence. Kết quả có thể là Failsafe không còn integration test phù hợp vì chúng chỉ tag `integration`.

Để tránh tình huống đó trong CI, có thể dùng profiles hoặc properties riêng trong POM để điều khiển nhóm tests của từng plugin một cách minh bạch. Sau đó kiểm tra số test ở cả `surefire-reports` và `failsafe-reports`.

### 8.2. Maven profile không thay thế tag

Một profile có thể chứa configuration:

```xml
<profiles>
    <profile>
        <id>fast-tests</id>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.2</version>
                    <configuration>
                        <groups>fast</groups>
                    </configuration>
                </plugin>
            </plugins>
        </build>
    </profile>
</profiles>
```

Đây là **đoạn đặt trong POM hiện hữu**, không phải file POM độc lập. Chạy `mvn -Pfast-tests test` sẽ kích hoạt profile rồi áp cấu hình Surefire. Nhưng `-Pfast-tests` vẫn là **Maven profile ID**, không phải annotation tag `fast-tests`.

Nếu cần một pipeline unit mặc định chạy mọi test, nên tránh profile `activeByDefault` phức tạp khiến việc bật CI profile bất ngờ tắt cấu hình khác ở cùng POM.

## 9. Ví dụ Java 17 hoàn chỉnh: nhìn thấy includes, excludes và @Tag hoạt động

Ví dụ này chạy được với **JDK 17+**, Maven 3.9.x, repository Maven có thể tải plugins và JUnit Jupiter. Sử dụng những class test không cần database/HTTP để kết quả ổn định, nhưng có đủ nhãn mô phỏng nhóm. Lớp integration kiểm tra kết hợp logic tính toán và ghi file bằng Java NIO (không cần database).

**Mục tiêu:**

- Surefire chọn `**/*Test.java` nhưng exclude `**/*ExperimentalTest.java`.
- JUnit Jupiter test classes được gắn các tags `fast`, `smoke`, `slow`, `edge`, `experimental`.
- Failsafe chạy `*IT.java` ở integration-test/verify.
- Quan sát số test khi dùng `-Dgroups=fast`, `-DexcludedGroups=slow` và `-Dtest`.
- Một chương trình Java main in chính xác `Test filters OK: 7`.

### 9.1. Cấu trúc thư mục

```text
test-filter-demo/
├── pom.xml
└── src/
    ├── main/java/vn/example/tests/
    │   ├── Calculator.java
    │   └── ReportWriter.java
    └── test/java/vn/example/tests/
        ├── CalculatorFastTest.java
        ├── CalculatorSlowTest.java
        ├── CalculatorEdgeTest.java
        ├── CalculatorExperimentalTest.java
        └── CalculatorIT.java
```

### 9.2. POM đầy đủ

File `test-filter-demo/pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>vn.example</groupId>
    <artifactId>test-filter-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.0</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-clean-plugin</artifactId>
                <version>3.3.2</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-resources-plugin</artifactId>
                <version>3.3.1</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
                <configuration>
                    <includes>
                        <include>**/*Test.java</include>
                    </includes>
                    <excludes>
                        <exclude>**/*ExperimentalTest.java</exclude>
                        <exclude>**/*IT.java</exclude>
                    </excludes>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.5.2</version>
                <executions>
                    <execution>
                        <id>integration-tests</id>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
                <configuration>
                    <includes>
                        <include>**/*IT.java</include>
                    </includes>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-jar-plugin</artifactId>
                <version>3.4.2</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Đọc POM:

- Surefire chọn 4 tên class `*Test.java`, nhưng exclude một lớp `*ExperimentalTest`, vậy **3 class unit** còn lại có thể chạy.
- `CalculatorIT.java` **không** được Surefire chọn vì suffix `*IT`; Failsafe chọn nó ở integration-test.
- Không cấu hình `groups` mặc định trong POM, nên `mvn test` chạy các test methods thuộc các class đã chọn **bất kể tag**, trừ disabled/conditional filters từ framework.
- Failsafe có hai goal gắn vào đúng default phases qua goal descriptors; `mvn verify` mới chạy toàn bộ phase và đánh giá kết quả.
- Tất cả Maven plugin versions được pin, thuận tiện tái hiện bài tập.

### 9.3. Class Java có thể chạy độc lập

File `src/main/java/vn/example/tests/Calculator.java`:

```java
package vn.example.tests;

public final class Calculator {
    private Calculator() {
    }

    public static int add(int a, int b) {
        return Math.addExact(a, b);
    }

    public static boolean isEven(int n) {
        return n % 2 == 0;
    }

    public static String format(int n) {
        return "n=" + n;
    }

    public static void main(String[] args) {
        System.out.println("Test filters OK: " + add(3, 4));
    }
}
```

File `src/main/java/vn/example/tests/ReportWriter.java`:

```java
package vn.example.tests;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ReportWriter {
    private ReportWriter() {
    }

    public static void write(Path file, int a, int b) throws IOException {
        String content = "result=" + Calculator.add(a, b);
        Files.writeString(file, content, StandardCharsets.UTF_8);
    }
}
```

`ReportWriter` kết hợp logic từ `Calculator` và Java NIO để minh họa integration test có I/O. Không cần HTTP service hoặc database thật; tag `integration` chỉ phân loại bài tập ở đây.

### 9.4. Fast + smoke: hai test methods

File `src/test/java/vn/example/tests/CalculatorFastTest.java`:

```java
package vn.example.tests;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("fast")
@Tag("smoke")
class CalculatorFastTest {
    @Test
    void addsNumbers() {
        assertEquals(7, Calculator.add(3, 4));
    }

    @Test
    void checksEvenNumber() {
        assertTrue(Calculator.isEven(8));
    }
}
```

Đây là **hai methods**; tag trên class được áp dụng cho cả hai. Chạy `-Dgroups=fast` hoặc `-Dgroups=smoke` đều có thể chọn cả hai methods.

### 9.5. Slow: một method

File `src/test/java/vn/example/tests/CalculatorSlowTest.java`:

```java
package vn.example.tests;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Tag("slow")
class CalculatorSlowTest {
    @Test
    void formatsDescription() {
        assertEquals("n=9", Calculator.format(9));
    }
}
```

Nhãn `slow` ở đây là **nhãn phân loại để minh họa filter**, không phải khẳng định phép nối chuỗi này thực sự chậm. Trong dự án thật, chỉ gắn slow cho test thực sự có workload/IO đắt.

### 9.6. Edge: một method

File `src/test/java/vn/example/tests/CalculatorEdgeTest.java`:

```java
package vn.example.tests;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Tag("edge")
class CalculatorEdgeTest {
    @Test
    void sumsOppositeValues() {
        assertEquals(0, Calculator.add(-4, 4));
    }
}
```

### 9.7. Experimental: có test nhưng bị excludes loại khỏi unit suite mặc định

File `src/test/java/vn/example/tests/CalculatorExperimentalTest.java`:

```java
package vn.example.tests;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Tag("experimental")
class CalculatorExperimentalTest {
    @Test
    void checksFormattingExperiment() {
        assertEquals("n=0", Calculator.format(0));
    }
}
```

Nó có thể compile thành class hợp lệ và có một JUnit test method. Nhưng cấu hình `<exclude>**/*ExperimentalTest.java</exclude>` **loại cả class khỏi Surefire run mặc định**. Đây là sự khác nhau giữa “test tồn tại trong source” và “test được thực thi”.

**Trong dự án thật**, không nên để nhóm experimental excluded vô thời hạn: cần review, tiêu chí bật lại và CI job chạy riêng khi thích hợp.

### 9.8. Integration: một method chạy bằng Failsafe

File `src/test/java/vn/example/tests/CalculatorIT.java`:

```java
package vn.example.tests;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Tag("integration")
class CalculatorIT {
    @TempDir
    Path tempDir;

    @Test
    void writesReportFile() throws Exception {
        Path file = tempDir.resolve("report.txt");
        ReportWriter.write(file, 4, 5);
        assertEquals(
            "result=9",
            Files.readString(file, StandardCharsets.UTF_8)
        );
    }
}
```

`@TempDir` do JUnit Jupiter cung cấp, nên test không phụ thuộc đường dẫn máy thật. Tên `*IT.java` phù hợp cách dùng Failsafe. Test kiểm tra logic tính toán kết hợp I/O file, không phải truy cập database.

### 9.9. Các lệnh chạy và số test mong đợi

Từ thư mục `test-filter-demo`, với Maven 3.9.x và JDK 17+:

```bash
java -version
mvn --version

# Unit-test suite mặc định: Fast 2 + Slow 1 + Edge 1 = 4 tests
mvn -B clean test

# Chỉ class có @Tag("fast"): 2 tests
mvn -B -Dgroups=fast test

# Loại các test có tag "slow": Fast 2 + Edge 1 = 3 tests
mvn -B -DexcludedGroups=slow test

# Chỉ một class: CalculatorSlowTest có 1 test method
mvn -B -Dtest=CalculatorSlowTest test

# Chỉ một method: 1 test
mvn -B -Dtest="CalculatorFastTest#addsNumbers" test

# Unit 4 tests và Failsafe Integration 1 test
mvn -B clean verify

# Chạy Java application không cần JUnit trong runtime
java -cp target/test-filter-demo-1.0.0.jar vn.example.tests.Calculator
```

**Stdout chính xác của lệnh Java cuối cùng** là:

```text
Test filters OK: 7
```

**Các số test ở trên là kết quả mong đợi cho file/POM trong bài** khi không có parent/profile/CLI khác ghi đè configuration và đúng phiên bản/provider được dùng. Chúng không phải toàn bộ log Maven. Maven sẽ còn in lifecycle logs, tải dependencies, test summaries và warnings tùy môi trường.

Với `mvn -B clean verify`: Surefire ở phase test chạy **4 unit test methods**, Failsafe ở phase integration-test chạy **1 integration test method**; các test reports được lưu riêng. Lớp Experimental không chạy trong unit suite mặc định, vì Surefire excludes. Lệnh `-Dgroups=fast test` chỉ chạy 2 test methods thuộc Fast; `-DexcludedGroups=slow test` vẫn chạy Fast và Edge.

**Không chạy thử bằng cách copy Java source vào một file duy nhất.** Các đường dẫn package/class ở trên phải được tạo thành những file riêng đúng vị trí. Project cần Maven tải JUnit Jupiter và build plugins ở lần build đầu tiên.

### 9.10. Báo cáo chứng minh test nào đã chạy

Sau khi `mvn test`:

```text
target/surefire-reports/
```

Sau `mvn verify` có thêm:

```text
target/failsafe-reports/
```

Trong các thư mục này, các báo cáo XML/TXT giúp xác nhận class nào, số methods nào, trạng thái pass/fail/skipped. Ví dụ muốn chắc chắn `CalculatorExperimentalTest` không chạy trong unit suite, hãy kiểm tra nó **không xuất hiện như một test executed trong surefire reports**, thay vì chỉ xem BUILD SUCCESS.

Có thể chạy lại unit suite với log rõ và lưu output CI theo cách quản lý artifacts tiêu chuẩn. Không viết báo cáo đè lên file Maven plugin tạo ra bằng tay.

### 9.11. Quan sát việc chọn lớp và filter tag riêng biệt

Bảng dự kiến cho ví dụ:

| Lệnh | Fast (2) | Slow (1) | Edge (1) | Experimental (1) | IT (1) |
| --- | --- | --- | --- | --- | --- |
| `mvn test` | Chạy | Chạy | Chạy | Loại bởi excludes | Chưa chạy Failsafe |
| `mvn -Dgroups=fast test` | Chạy | Không | Không | Loại bởi excludes | Chưa chạy Failsafe |
| `mvn -DexcludedGroups=slow test` | Chạy | Không | Chạy | Loại bởi excludes | Chưa chạy Failsafe |
| `mvn -Dtest=CalculatorSlowTest test` | Không | Chạy | Không | Không | Chưa chạy Failsafe |
| `mvn verify` | Chạy | Chạy | Chạy | Loại bởi excludes | Chạy bằng Failsafe |

**Trường hợp ngoại lệ:** `-Dtest=CalculatorExperimentalTest` có thể buộc chọn một lớp bị excludes loại ở default run, vì `test` có thể override include/exclude thông thường. Đó là hành vi tiện lợi cho debug, không phải lời khuyên đưa class experimental vào pipeline mặc định.

## 10. includes/excludes nên phối hợp tags thế nào trong dự án lớn?

Một quy ước thường bền hơn những pattern phức tạp:

1. **Tên lớp quyết định vòng lifecycle:** `*Test` cho unit ở Surefire, `*IT` cho integration ở Failsafe.
2. **Tag quyết định phân khúc bên trong vòng đó:** `fast`, `smoke`, `slow`, `db`, `edge`.
3. **Mặc định CI chạy đủ kiểm thử cần thiết:** đừng loại 90% tests chỉ để có job xanh nhanh.
4. **Job nhanh được thiết kế rõ:** dùng `groups=fast` trong job commit nhanh, còn nightly/release chạy full suite.
5. **Một test có nhiều tag nếu cần:** ví dụ `@Tag("fast")` và `@Tag("smoke")` không phải hai method khác nhau.
6. **Tag không nói lên execution engine:** JUnit 4, Jupiter và TestNG cần provider/engine phù hợp.
7. **Báo cáo test counts:** nếu sau một thay đổi POM số tests giảm bất thường, coi đó là tín hiệu QA.
8. **Ghi lý do excludes:** tránh exclude test flaky vĩnh viễn và lãng quên.
9. **Không phụ thuộc thứ tự test:** test phải độc lập về state hoặc setup/teardown được quản lý minh bạch.
10. **Giữ profile/config dễ audit:** ít tầng override, pin versions, kiểm tra effective POM.

### 10.1. Ví dụ phân tầng CI

| Job | Lệnh minh họa | Kết quả mong muốn |
| --- | --- | --- |
| Commit nhanh | `mvn -Dgroups=fast test` | Phản hồi sớm, không thay thế full suite |
| PR unit đầy đủ | `mvn test` | Chạy mọi unit test được Surefire chọn |
| Integration | `mvn verify` | Gồm Failsafe `*IT` và unit tests |
| Nightly | `mvn verify` với môi trường đầy đủ | Bật các tests cần database/container, không che excludes |
| Debug | `mvn -Dtest=ClassName test` | Lặp đúng test đang điều tra |

Trong môi trường có resource ngoài, các job integration có thể cần containers, credentials, network hoặc test data. Những điều kiện này thuộc **test fixture/CI orchestration**, không phải chức năng tự động của `includes` và `@Tag`.

### 10.2. Khi cần excludesFile/includesFile

Surefire hỗ trợ đọc danh sách test patterns từ file ngoài bằng `includesFile`/`excludesFile` trên các version hỗ trợ. Chúng hữu ích khi danh sách quá dài để đặt trong POM, nhưng cần quản lý file trong source control, giải thích lý do và kiểm tra format mỗi dòng với tài liệu đúng plugin.

Không dùng một danh sách excludes ngoài POM không ai review; nó dễ làm test suite “thành công” dù những test quan trọng không còn được chạy.

## 11. Sai sót thường gặp với tag expressions và XML

### 11.1. Quên escape dấu &

Sai XML:

```xml
<groups>fast & !db</groups>
```

Đúng XML:

```xml
<groups>fast &amp; !db</groups>
```

Lỗi này xảy ra **trước JUnit discovery**, trong quá trình Maven parse POM. Không giải quyết nó bằng cách đổi version JUnit.

### 11.2. Dùng -Dtags thay vì -Dgroups

Đối với Surefire + JUnit Platform, tài liệu chính thức chỉ rõ **`groups`** chọn tags và **`excludedGroups`** loại tags. Nếu không có plugin/extension khác cung cấp property riêng, lệnh `-Dtags=fast` không phải thay thế mặc định cho `-Dgroups=fast`. Một CLI property không được plugin tham chiếu có thể bị bỏ qua.

### 11.3. Đổi includes làm mất default patterns

Khi thêm `<includes><include>**/*Test.java</include></includes>`, các class `TestOrder.java` hoặc `OrderTests.java` có thể không còn khớp. Hãy kiểm kê tên file hoặc thêm các pattern thực sự cần thiết. Không đoán rằng Surefire tự cộng thêm mọi mẫu mặc định vào danh sách do bạn khai báo.

### 11.4. Gắn @Tag nhưng quên include class

Một class tên `OrderSpec.java` có `@Tag("fast")` không tự được Surefire chọn theo bốn mẫu mặc định. Sửa tên lớp, thêm include phù hợp hoặc dùng selection cụ thể. Tag filter chỉ có cơ hội tác dụng **sau khi class đã được discovery**.

### 11.5. Gắn @Tag("integration") nhưng để class *Test

Nếu class được đặt tên `DatabaseIntegrationTest.java`, nó có thể lọt Surefire mặc định vì suffix `*Test`, dù tag là integration. Để tránh chạy DB test trong unit phase, dùng tên `*IT`/Failsafe hoặc cấu hình excludes/filters rõ. **Tag tự nó không phải mệnh lệnh “chạy ở phase integration-test”.**

### 11.6. Có nhiều framework nhưng thiếu provider/engine

JUnit Jupiter test phải có engine thích hợp (thường qua `junit-jupiter` dependency), JUnit 4 khi chạy trong mô hình JUnit Platform cần Vintage Engine, TestNG cần engine/provider phù hợp phiên bản Surefire. Không được đổ lỗi cho includes nếu class được quét nhưng không được engine nhận test method.

### 11.7. Skip khác filter

- `-DskipTests`: bỏ qua thực thi tests theo plugin handling; test sources vẫn thường được compile.
- `-Dmaven.test.skip=true`: bỏ qua cả việc compile tests trong các plugin hỗ trợ và bỏ test execution.
- `-Dgroups=fast`: **chạy những tests được chọn**, không có nghĩa “skip tất cả test”.
- `-Dtest=SpecificTest`: chọn một subset tường minh, không xóa source tests còn lại.

Không dùng skip hoàn toàn trong pipeline mà project cần kiểm định chất lượng.

## 12. Troubleshooting: khi số test bằng 0 hoặc kết quả khác mong đợi

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `Tests run: 0` dù có nhiều test files | Tên không match `includes` hoặc exclusions quá rộng | Đối chiếu class names với patterns; dùng reports |
| Thêm tag `fast` nhưng test không chạy | Class bị excludes, hoặc provider không nhận test | Xem class filter rồi JUnit engine/tag filter |
| `mvn -Dgroups=fast test` không chạy lớp `OrderTest` | Lớp không gắn tag fast | Kiểm tra annotation ở class/method |
| `mvn test` vẫn chạy DB integration | Tên `*Test` trùng default, tag không tự exclude | Đặt `*IT`, Failsafe hoặc excludes rõ |
| `-Dtest=Name` báo no tests matching | Typo, sai class/package, module không có test | Kiểm tra `target/test-classes`, module, `failIfNoSpecifiedTests` |
| Class Experimental không chạy nhưng có JAR/test class | Bị excludes trong Surefire | Đây là kỳ vọng, muốn chạy riêng dùng selection có chủ đích |
| Failsafe `*IT` không chạy khi gọi `mvn test` | Failsafe bind ở integration-test/verify, chưa tới phase | Chạy `mvn verify` |
| Báo lỗi XML khi dùng `fast & !slow` | Chưa escape `&amp;` | Sửa POM XML syntax |
| `groups=smoke` có ý nghĩa khác giữa JUnit4/TestNG | JUnit4 category FQCN, TestNG group String | Dùng framework-specific docs |
| Bật `-Pfast-tests` nhưng không chọn được tag | Profile chưa gắn Surefire `groups` hoặc bị override | Xem effective POM, active profiles |
| JUnit 4 test không được chạy cùng Jupiter | Thiếu Vintage Engine/provider theo plugin version | Bổ sung đúng engine/dependency |
| Lọc đúng class nhưng không chạy đúng method | Tag/disabled/conditional/parameterized tests | Xem test engine behavior và XML reports |
| Tên `*IT` được Surefire chạy bất ngờ | Đã thêm include rộng `**/*` hoặc `-Dtest` | Rà soát actual includes/CLI |
| Maven BUILD SUCCESS nhưng không test nào chạy | Skip flags, includes sai, `failIfNoTests=false` | Ghi test count quality gate trong CI |

### 12.1. Quy trình chẩn đoán theo thứ tự

**Bước 1 — xác định module, plugin version, command:**

```bash
mvn --version
mvn help:effective-pom -Doutput=target/effective-pom.xml
```

Tìm `maven-surefire-plugin`, `maven-failsafe-plugin`, version, includes/excludes/groups/excludedGroups sau parent/profile merge. Goal `help:effective-pom` cần Help Plugin tải được.

**Bước 2 — kiểm tra source/class names:**

```text
src/test/java/.../OrderFastTest.java
src/test/java/.../OrderIT.java
target/test-classes/.../OrderFastTest.class
target/test-classes/.../OrderIT.class
```

Kiểm tra file nào compile thành công. Đừng chỉ nhìn tên lớp trong IDE nếu build có custom testSourceDirectory hoặc generated tests.

**Bước 3 — chạy một test cụ thể:**

```bash
mvn -Dtest=CalculatorFastTest test
```

Nếu lệnh này chạy nhưng `mvn test` mặc định không chạy, điều tra includes/excludes. Nếu cả hai đều fail, kiểm tra compile, dependencies, provider/engine và test annotation.

**Bước 4 — chạy tag cụ thể và kiểm tra reports:**

```bash
mvn -Dgroups=fast test
```

Đọc `target/surefire-reports` xem tests executed, skipped, failures/errors. Đừng suy từ một dòng `BUILD SUCCESS` rằng test quan trọng đã chạy.

**Bước 5 — xem Failsafe và phases:**

```bash
mvn verify
```

Kiểm tra `target/failsafe-reports` và các file `*IT.java`. Nếu test cần service ngoài, bảo đảm CI startup/teardown đúng và chạy tới `verify`.

**Bước 6 — debug khi cần:**

```bash
mvn -X -B test
```

Log debug có thể hiển thị Surefire config, includes/excludes và provider, nhưng cũng có thể lộ local paths, URL hạ tầng hoặc thông tin nhạy cảm. Lọc secrets trước khi chia sẻ.

## 13. Best practices để test suite đáng tin

1. Dùng quy ước tên `*Test` và `*IT` rõ ràng, hạn chế các include patterns không cần thiết.
2. Giữ hai tầng selection tách bạch: **class glob** và **framework tag/group**.
3. Gắn tag có ý nghĩa theo chi phí và điều kiện của test, không theo cảm giác.
4. Đảm bảo một job CI định kỳ **chạy full suite**, không chỉ fast/smoke.
5. Review mọi excludes và đặt ngày/điều kiện bật lại nếu tạm loại test lỗi.
6. Đừng dùng `@Disabled` để né test khó; nếu có lý do, kèm issue/giải thích trong code review.
7. Pin versions của Surefire, Failsafe, JUnit/TestNG và Java release.
8. Xác minh JUnit engines/provider trong project đa framework khi upgrade Surefire 3.5.x → 3.6.x.
9. Bắt CI phát hiện test counts giảm bất thường hoặc không có test phù hợp.
10. Với Failsafe, chạy `verify` đầy đủ để báo lỗi chính xác và đảm bảo cleanup.
11. Đừng truyền `-Dgroups` toàn bộ reactor mà không kiểm tra nó ảnh hưởng Surefire/Failsafe và mỗi module thế nào.
12. Với multi-module, `-Dtest` có thể không match ở một số modules; chỉ định `-pl` hoặc cấu hình `failIfNoSpecifiedTests` có kiểm soát khi debug.
13. Tránh test phụ thuộc môi trường local ẩn; unit tests nên chạy không cần DB/CI secret.
14. Đối chiếu report XML trước và sau khi đổi POM, không chỉ kiểm tra compile success.

## 14. Câu hỏi tự luyện và đáp án

**Câu 1.** Một class `OrderSpec.java` có `@Tag("fast")`. Với Surefire mặc định, chạy `mvn -Dgroups=fast test` có chắc chạy test này không?

**Đáp án:** Không. `OrderSpec` không khớp bốn mẫu tên mặc định. Cần đổi tên hoặc thêm include trước; tag chỉ lọc sau khi class được khám phá.

**Câu 2.** Surefire có `<includes>**/*Test.java</includes>` và `<excludes>**/*ExperimentalTest.java</excludes>`. `OrderExperimentalTest` có `@Tag("fast")`. Khi chạy mặc định với groups fast, nó có được chạy không?

**Đáp án:** Không. Class bị loại bởi excludes trước tầng JUnit tag. Một selection rõ `-Dtest` có thể thay quy tắc lớp thông thường, nhưng đừng dựa vào tag để vượt excludes.

**Câu 3.** JUnit Jupiter `@Tag("db")` và TestNG `@Test(groups="db")` có phải cùng annotation không?

**Đáp án:** Không. Chúng thuộc framework khác nhau, dù Surefire đều có thể dùng tham số `groups` để lọc nhãn phù hợp khi provider hỗ trợ.

**Câu 4.** Tại sao `<groups>fast & !slow</groups>` gây lỗi POM, còn `<groups>fast &amp; !slow</groups>` hợp lệ?

**Đáp án:** Dấu ampersand `&` phải được escape trong XML text thành `&amp;`. Sau khi parse XML, provider nhận tag expression `fast & !slow`.

**Câu 5.** `mvn test` chạy unit tests nhưng không chạy `BillingIT.java`. Maven có bỏ sót integration test không?

**Đáp án:** Không nhất thiết. `mvn test` chưa tới Failsafe integration-test/verify. Chạy `mvn verify` nếu Failsafe đã được bind phù hợp.

**Câu 6.** Lệnh `mvn -Dtest=CalculatorFastTest#addsNumbers test` nên chạy bao nhiêu method trong ví dụ?

**Đáp án:** Một method `addsNumbers` trong class `CalculatorFastTest`, nếu provider/version hỗ trợ method selection và không có filter khác chặn nó.

**Câu 7.** Trong JUnit 4, `@Category(SlowTests.class)` có thể lọc bằng `<groups>slow</groups>` như Jupiter không?

**Đáp án:** Không theo cơ chế category type. Cần dùng class name của marker, ví dụ `<groups>vn.example.legacy.SlowTests</groups>`.

**Câu 8.** Vì sao một job CI chỉ chạy `-Dgroups=fast` không được coi là đã kiểm thử đầy đủ?

**Đáp án:** Nó chỉ chạy các tests có tag fast sau khi lọc lớp; các nhóm slow/edge/integration hoặc test chưa gắn tag có thể không được chạy. Cần job full suite có reports và policy rõ ràng.

## Tài liệu chính thức

- [Apache Maven Surefire — Inclusions and Exclusions of Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html)
- [Apache Maven Surefire — Running a Single Test](https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html)
- [Apache Maven Surefire — Using JUnit 5 Platform / Filtering by Tags](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Apache Maven Surefire — Using JUnit 4 / Categories](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit.html)
- [Apache Maven Surefire — Using TestNG / Groups](https://maven.apache.org/surefire/maven-surefire-plugin/examples/testng.html)
- [Apache Maven Surefire — surefire:test Goal Parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Apache Maven Failsafe — Inclusions and Exclusions](https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html)
- [Apache Maven Failsafe — Goals Overview](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [JUnit 5 — Tagging and Filtering](https://docs.junit.org/5.11.0/user-guide/#writing-tests-tagging-and-filtering)
