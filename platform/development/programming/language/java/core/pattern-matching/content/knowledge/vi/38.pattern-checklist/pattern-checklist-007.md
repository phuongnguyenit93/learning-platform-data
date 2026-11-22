# Checklist tương thích phiên bản cho Java Pattern Matching

## 1. Vì sao phải kiểm tra phiên bản trước khi dùng pattern matching?

Một đoạn Java có thể biên dịch trên máy người viết nhưng không biên dịch trong CI, không chạy trong Docker, hoặc không được khách hàng sử dụng thư viện tải lên JVM cũ. Với pattern matching, nguyên nhân thường là **nhầm các mốc Java khác nhau**:

- `switch expression` dùng mũi tên `->` đã được chuẩn hóa trước Java 21.
- `instanceof String s` và `record Point(...)` cùng chính thức từ Java 16.
- Sealed classes/interfaces chính thức từ Java 17, nhưng **pattern matching cho switch chưa chính thức ở Java 17**.
- `case Point(var x, var y)`, guard `when` và nested record patterns được chuẩn hóa từ **Java 21**.
- Cú pháp `_` cho unnamed patterns được chuẩn hóa sau Java 21, không phải chỉ vì đang dùng JDK 21 mà được phép viết mọi dạng pattern.

Vì vậy, để đánh giá “tương thích phiên bản”, phải kiểm tra **cú pháp nguồn, tính năng preview/final, compiler JDK, release target, class-file version, thư viện chuẩn, dependency, build tool, test runner và JVM thực sự triển khai**. Một lần chạy trên laptop chưa phải chứng cứ sản phẩm tương thích với baseline đã công bố.

Bài này là một checklist thực hành cho module **Java Core Pattern Matching**: xác định mốc Java tối thiểu, lựa chọn Java 17 hoặc Java 21, dùng `javac --release`, kiểm tra null/guard/dominance, chạy hai chương trình cho cùng output, thiết lập Maven/Gradle/CI và tránh lỗi migration.

**Quy ước:** Những số phiên bản trong bảng là mốc **chính thức (final)** của tính năng. Bài không khẳng định JDK nào là phiên bản mới nhất tại một thời điểm. Nếu chuẩn bị phát hành thật, phải kiểm tra chính sách hỗ trợ của vendor JDK và môi trường triển khai cụ thể.

## 2. Bảng mốc tính năng chính thức

| Tính năng | Cú pháp minh họa | JDK final đầu tiên | JEP |
| --- | --- | --- | --- |
| Switch expression | `int n = switch (day) { case MONDAY -> 1; default -> 0; };` | **Java 14** | JEP 361 |
| Pattern matching cho `instanceof` | `obj instanceof String s` | **Java 16** | JEP 394 |
| Record classes | `record Point(int x, int y) {}` | **Java 16** | JEP 395 |
| Sealed classes và interfaces | `sealed interface Shape permits Circle {}` | **Java 17** | JEP 409 |
| Pattern matching cho `switch` | `case String s -> ...` | **Java 21** | JEP 441 |
| Guard `when` của pattern switch | `case String s when s.isBlank() -> ...` | **Java 21** | JEP 441 |
| Record patterns | `Point(var x, var y)` | **Java 21** | JEP 440 |
| Nested record patterns | `Box(Point(var x, var y))` | **Java 21** | JEP 440 |
| Unnamed variables và unnamed patterns | Pattern dùng `_` | **Java 22** | JEP 456 |

Ba cặp rất dễ bị nhầm:
1. **Switch expression không phải pattern switch.** Java 14 hỗ trợ tính giá trị từ switch với enum/int/String phù hợp, nhưng không final hỗ trợ `case Circle c` trong switch.
2. **Record không phải record pattern.** Java 16 cho phép khai báo và sử dụng `record Point(int x, int y)`, nhưng `Point(var x, var y)` cần Java 21 chính thức.
3. **Sealed không phải guarded switch.** Java 17 cho phép `sealed interface`, nhưng `case Type t when ...` là cú pháp Java 21 final.

**Không cần `--enable-preview`** để dùng bất kỳ tính năng nào trong bảng **khi build đúng phiên bản final hoặc mới hơn có hỗ trợ nó**, với lưu ý Java 21 không hỗ trợ unnamed patterns đã final ở Java 22. Không ép preview vào build production khi feature đã ổn định.

### Ví dụ tối thiểu theo từng baseline

**Java 16 trở lên — `instanceof` pattern:**

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

**Java 17 trở lên — sealed model:**

```java
sealed interface Result permits Success, Failure {}
record Success(String message) implements Result {}
record Failure(String reason) implements Result {}
```

**Java 21 trở lên — switch có guard:**

```java
String label = switch (value) {
    case null -> "null";
    case String text when text.isBlank() -> "blank";
    case String text -> "text";
    default -> "other";
};
```

Trong ví dụ Java 21, nhánh guard `String text when ...` phải đứng trước nhánh String tổng quát để không bị dominated. `case null` là quyết định tường minh về selector null, không dựa vào default.

## 3. Lịch sử preview không đồng nghĩa với hỗ trợ mặc định

Pattern matching cho switch từng trải qua nhiều giai đoạn preview:

| JDK | JEP | Trạng thái |
| --- | --- | --- |
| Java 17 | 406 | Preview lần đầu |
| Java 18 | 420 | Preview lần hai |
| Java 19 | 427 | Preview lần ba |
| Java 20 | 433 | Preview lần bốn |
| Java 21 | 441 | Final |

Record patterns:
- Java 19: JEP 405 — preview;
- Java 20: JEP 432 — preview lần hai;
- Java 21: JEP 440 — final.

**Hệ quả:** một ví dụ dùng record pattern có ghi “Java 19” có thể đòi `--enable-preview` trên JDK 19 và cú pháp/semantics phù hợp bản preview ấy. Không được giả định code đó dùng được mặc định trên JDK 19, hoặc có thể chép nguyên sang Java 21 mà không kiểm tra.

Cú pháp guard là một ví dụ quan trọng. Với **Java 21 final**, dạng cần nhớ là:

```java
case String s when s.length() >= 3 -> "long";
```

Không lấy nguyên hướng dẫn dùng guard từ một bản preview cũ rồi áp vào Java 21 chỉ vì cùng chủ đề pattern matching.

### Khi nào dùng `--enable-preview`?

Chỉ khi dự án **chủ động dùng một tính năng đang preview trong chính phiên bản JDK hiện hành**. Khi đó thường cần đồng bộ compile, test và runtime flags, đồng thời chấp nhận rủi ro tính năng thay đổi giữa releases.

Ví dụ cấu trúc lệnh dành cho **một tính năng preview thực sự thuộc JDK 21**:

```bash
javac --enable-preview --release 21 PreviewExample.java
java --enable-preview PreviewExample
```

Đây là **mẫu minh họa flag**, không phải chương trình chạy độc lập và **không cần áp dụng** cho record patterns hoặc pattern switch final trong Java 21. Nó cũng không cho phép compiler Java 21 biên dịch cú pháp preview của một bản JDK tùy ý khác.

Bản preview có thể cần cập nhật khi nâng JDK; không nên xem một file class chứa preview feature như artifact tương thích không giới hạn với mọi bản JVM tương lai. Với thư viện dùng rộng, tính năng final thường là lựa chọn an toàn hơn.

## 4. Năm lớp tương thích cần xác minh

Có thể xem đường đi của mã như sau:

```text
Java source: syntax, patterns, guards
          |
          v
Compiler JDK và --release
          |
          v
Class files + Java SE platform APIs
          |
          v
Libraries, plugins, processors, frameworks
          |
          v
CI test runner + JVM/Docker/server triển khai
```

**Nguồn:** Nếu code chứa `case T(var x)`, target Java 17 không chấp nhận cú pháp final Java 21. Việc compiler cài JDK 21 không làm syntax này trở nên “Java 17 compatible”.

**Compiler:** `javac --release 21` chỉ dùng được với JDK compiler hiểu release 21. JDK 17 không thể tạo class target 21 bằng một flag khác.

**Class files:** Mã target Java 17 có major class-file version **61**; target Java 21 là **65**. JVM 17 không chạy trực tiếp class file 65, thường báo `UnsupportedClassVersionError`.

**Platform APIs:** Một chương trình có cú pháp Java 17 vẫn có thể gọi API chuẩn được thêm ở Java mới nếu compiler không khóa đúng API của target. `--release` giúp phát hiện loại sai này trong build.

**Dependency/runtime:** Framework cũ hoặc bytecode instrumentation chưa hỗ trợ class version 65 có thể fail dù source đã biên dịch. Docker runtime có thể là JVM 17 dù build stage là JDK 21. Phải test artifact đúng nơi nó được chạy.

**Tóm lại:** Tương thích nguồn không bằng tương thích bytecode; tương thích bytecode không tự bảo đảm thư viện chuẩn/dependency; cả ba cũng không thay thế được kiểm chứng runtime thật.

## 5. Chọn Java baseline từ yêu cầu sản phẩm

Quyết định đầu tiên là **JVM thấp nhất mà artifact phải hỗ trợ**.

| Yêu cầu | Baseline nên cân nhắc | Hệ quả với pattern matching |
| --- | --- | --- |
| Ứng dụng cần chạy Java 17 và không preview | `--release 17` | Dùng `instanceof` patterns, records, sealed và switch expressions theo kiểu được hỗ trợ |
| Ứng dụng chạy Java 21+ | `--release 21` | Có thể dùng pattern switch, nested record patterns, guard `when` |
| Thư viện phải dùng được bởi khách hàng Java 17 | Build artifact Java 17 | Không đưa class target 21 vào đường thực thi JVM 17 |
| Ứng dụng cần tính năng Java 22 final | Target ít nhất 22 | Không quảng bá artifact là Java 21-compatible nếu dùng cú pháp/API mới |
| Đang thử preview | Khóa đúng JDK + flags + test | Không ngầm coi preview là stable contract |

**Không thể** dùng JDK 21 biên dịch cú pháp Java 21 thành một artifact Java 17 chỉ bằng cách đặt `-target 17`. Nếu dùng `--release 17`, compiler sẽ chặn cú pháp không thuộc Java 17, đúng mục đích của nó.

Nếu có cả module Java 17 và Java 21 trong monorepo, chúng có thể dùng toolchains khác nhau. Nhưng module chạy trên Java 17 không thể phụ thuộc bắt buộc vào class version 65 nếu nó phải load class đó trên JVM 17.

### Java 17 LTS hay Java 21 LTS?

Cả hai đều là các mốc LTS thông dụng của hệ sinh thái Java, nhưng dự án còn phải xét **chính sách vendor, dependency, chi phí triển khai và người dùng cuối**. “LTS” không đồng nghĩa với mọi phần mềm hỗ trợ mọi feature hoặc không cần kiểm chứng.

Khi đã quyết định nâng baseline từ 17 lên 21, hãy ghi rõ trong README, release notes, packaging/runtime docs. Với một thư viện công khai, thay minimum Java version là thay đổi compatibility lớn đối với consumer còn chạy JVM 17.

## 6. `javac --release` thay vì chỉ `-source` và `-target`

Lệnh tương thích Java 17:

```bash
javac --release 17 -encoding UTF-8 Java17FallbackDemo.java
```

`--release 17` điều khiển **source language rules, class-file target và API Java SE của release 17** mà compiler hỗ trợ. Đây là lựa chọn hợp lý khi một thư viện cần chạy trên Java 17.

Chỉ viết:

```bash
javac -source 17 -target 17 Java17FallbackDemo.java
```

không có cùng mức bảo đảm cho API platform: nếu đang chạy compiler trên JDK mới mà không giới hạn đúng thư viện chuẩn, code vẫn có thể vô tình gọi method Java SE mới hơn rồi fail trên JVM 17.

**Giới hạn:** `--release` không kiểm tra mọi thư viện bên thứ ba, reflection, service loader, native code, processor hoặc runtime configuration. Vẫn cần test thực sự ở JVM thấp nhất.

### Ba thông tin phải có khi điều tra build

```bash
java -version
javac -version
```

Cùng với release flag thực tế, xác nhận:
- `java` đang chạy từ đường dẫn nào;
- `javac` là compiler nào;
- Build tool có dùng toolchain hoặc fork compiler khác không;
- Môi trường thực thi JAR có cùng yêu cầu Java tối thiểu không.

Ví dụ “IDE hiển thị Project SDK 21” không chứng minh CI Maven đang dùng compiler 21, cũng không chứng minh Docker runtime >= 21.

## 7. Chương trình A: Java 17 tương thích không cần preview

Ta thiết kế một tập lệnh: tạo đơn, hủy đơn và giao hàng. Dữ liệu được khai báo bằng `record`, tập biến thể bằng `sealed interface`. Vì target 17, việc phân loại dùng **type patterns của `instanceof`**.

Tạo file **`Java17FallbackDemo.java`**:

```java
public class Java17FallbackDemo {

    sealed interface Action permits Create, Cancel, Ship {}

    record Address(String city) {}

    record Create(String id, int quantity) implements Action {}

    record Cancel(String id) implements Action {}

    record Ship(String id, Address address) implements Action {}

    static String describe(Action action) {
        if (action == null) {
            return "NULL";
        }

        if (action instanceof Create created) {
            if (created.quantity() <= 0) {
                return "INVALID_CREATE:" + created.id();
            }
            return "CREATE:" + created.id();
        }

        if (action instanceof Cancel cancelled) {
            return "CANCEL:" + cancelled.id();
        }

        if (action instanceof Ship shipment) {
            Address address = shipment.address();
            if (address != null
                    && address.city() != null
                    && !address.city().isBlank()) {
                return "SHIP:" + shipment.id()
                    + "@" + address.city();
            }
            return "SHIP_WITHOUT_CITY:" + shipment.id();
        }

        throw new IllegalStateException(
            "Unsupported action: " + action.getClass());
    }

    public static void main(String[] args) {
        System.out.println(describe(new Create("O-1", 2)));
        System.out.println(describe(new Create("O-2", 0)));
        System.out.println(describe(new Cancel("O-3")));
        System.out.println(
            describe(new Ship("O-4", new Address("Huế"))));
        System.out.println(describe(new Ship("O-5", null)));
        System.out.println(
            describe(new Ship("O-6", new Address(null))));
        System.out.println(describe(null));
    }
}
```

Biên dịch bằng **JDK 17 hoặc compiler mới hơn có hỗ trợ `--release 17`**:

```bash
javac --release 17 -encoding UTF-8 Java17FallbackDemo.java
java Java17FallbackDemo
```

**Đầu ra dự kiến:**

```text
CREATE:O-1
INVALID_CREATE:O-2
CANCEL:O-3
SHIP:O-4@Huế
SHIP_WITHOUT_CITY:O-5
SHIP_WITHOUT_CITY:O-6
NULL
```

Vì sao tương thích Java 17:
- `sealed interface` đã final ở 17;
- `record` và `instanceof` patterns đã final ở 16;
- Không dùng record patterns hoặc pattern switch;
- Null selector được xử lý bằng `if` rõ ràng.

Đây là **mã minh họa tương thích**, không phải một domain model đã xác thực hoàn chỉnh. `Ship(null)` và `Address(null)` được cho phép để kiểm tra hai trạng thái null khác nhau. Trong domain thật, constructor có thể cấm chúng và API boundary xử lý invalid input trước khi tạo object.

**Điểm hạn chế:** Chuỗi `if/instanceof` kết thúc bằng fallback runtime. Khi thêm một permitted subtype mới, compiler không tự buộc thêm một nhánh trong logic `if` này. Test và code review phải bảo đảm không bỏ sót subtype.

## 8. Chương trình B: Java 21 với record patterns, `switch` và `when`

Dùng cùng model và cùng kết quả, nhưng Java 21 cho phép biểu diễn việc chọn nhánh trực tiếp bằng `switch expression`.

Tạo file **`Java21PatternCompatibilityDemo.java`**:

```java
public class Java21PatternCompatibilityDemo {

    sealed interface Action permits Create, Cancel, Ship {}

    record Address(String city) {}

    record Create(String id, int quantity) implements Action {}

    record Cancel(String id) implements Action {}

    record Ship(String id, Address address) implements Action {}

    static String describe(Action action) {
        return switch (action) {
            case null -> "NULL";

            case Create(var id, var quantity)
                    when quantity <= 0 ->
                "INVALID_CREATE:" + id;

            case Create(var id, var quantity) ->
                "CREATE:" + id;

            case Cancel(var id) ->
                "CANCEL:" + id;

            case Ship(var id, Address(var city))
                    when city != null && !city.isBlank() ->
                "SHIP:" + id + "@" + city;

            case Ship(var id, var address) ->
                "SHIP_WITHOUT_CITY:" + id;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Create("O-1", 2)));
        System.out.println(describe(new Create("O-2", 0)));
        System.out.println(describe(new Cancel("O-3")));
        System.out.println(
            describe(new Ship("O-4", new Address("Huế"))));
        System.out.println(describe(new Ship("O-5", null)));
        System.out.println(
            describe(new Ship("O-6", new Address(null))));
        System.out.println(describe(null));
    }
}
```

Biên dịch bằng **JDK 21 trở lên có hỗ trợ target 21**:

```bash
javac --release 21 -encoding UTF-8 Java21PatternCompatibilityDemo.java
java Java21PatternCompatibilityDemo
```

**Đầu ra dự kiến — giống chương trình Java 17:**

```text
CREATE:O-1
INVALID_CREATE:O-2
CANCEL:O-3
SHIP:O-4@Huế
SHIP_WITHOUT_CITY:O-5
SHIP_WITHOUT_CITY:O-6
NULL
```

### Những tính năng Java 21 đang được dùng

- `case Create(var id, var quantity)` và `case Ship(var id, Address(var city))`: record patterns.
- `case ... when ...`: guarded patterns.
- `case null`: chính sách selector null tường minh.
- `return switch (action) { ... };`: switch expression kết hợp patterns.
- `Action` là sealed hierarchy và các nhánh non-null bao phủ mọi subtype, nên switch exhaustive và không cần `default`.

**Không cần `--enable-preview`** vì các tính năng trên đã final trong Java 21.

### Vì sao thứ tự case quan trọng?

`case Create(...) when quantity <= 0` phải nằm trước `case Create(...)` không guard. Nếu đảo lại, nhánh tổng quát đã bao phủ mọi Create, nhánh đặc thù phía sau bị **dominated** và compiler có thể báo lỗi.

Tương tự, `case Ship(var id, Address(var city)) when ...` cần đứng trước `case Ship(var id, var address)`. Nhánh Ship tổng quát là fallback cho những giá trị không thỏa điều kiện ưu tiên.

### Null ở record con khác guard false

- Với `new Ship("O-5", null)`: nested record pattern `Address(var city)` **không khớp**, vì `address` null. Guard không được đánh giá; nhánh Ship tổng quát được chọn.
- Với `new Ship("O-6", new Address(null))`: nested pattern **khớp** Address, biến `city` có thể nhận null. Guard `city != null` false; nhánh Ship tổng quát được chọn.

Hai đường đi khác nhau nhưng cùng output. Khi migration từ Java 17 sang 21, cần test cả **pattern fail** và **guard false**, không chỉ một trường hợp thiếu địa chỉ.

### Exhaustive switch khi thêm subtype

Nếu thêm `record Refund(String id) implements Action` và cập nhật `permits`, switch expression hiện tại có thể không còn exhaustive. Compiler buộc xem xét thêm nhánh Refund. Đây là lợi ích so với chuỗi `if/instanceof` tự viết, vốn có thể chỉ phát hiện thiếu nhánh ở runtime.

Đừng thêm `default -> "UNKNOWN"` chỉ để compiler im lặng nếu nghiệp vụ cần xử lý subtype mới một cách tường minh.

## 9. So sánh tương thích hành vi trước và sau refactor

Cùng một kết quả console không chứng minh toàn bộ nghiệp vụ tương đương. Khi migrate, dùng bộ test có assertions:

| Dữ liệu | Java 17 | Java 21 | Điều cần kiểm chứng |
| --- | --- | --- | --- |
| Create quantity 2 | `instanceof Create` | `case Create` | `CREATE:O-1` |
| Create quantity 0 | `if quantity<=0` | `when quantity<=0` | `INVALID_CREATE:O-2` |
| Cancel | `instanceof Cancel` | `case Cancel` | `CANCEL:O-3` |
| Ship có city | Accessor + null checks | Nested pattern + guard | `SHIP:O-4@Huế` |
| Ship address null | `address != null` false | Nested pattern fail | Fallback |
| Ship city null | `city != null` false | Guard false | Fallback |
| Selector null | `if action==null` | `case null` | `NULL` |
| Thêm subtype | Fallback runtime | Exhaustiveness compile | Nhánh nghiệp vụ mới |

Nếu method có side effects, phải kiểm tra cả thứ tự gọi repository/audit, exception, transaction và idempotency. Refactor cú pháp không miễn trừ bảo toàn hành vi.

Record pattern cũng truy cập component qua accessor. Với accessor custom có side effect hoặc chi phí cao, deconstruction có thể ảnh hưởng hiệu năng hoặc thời điểm exception. Hãy giữ accessor ổn định, đọc đúng contract; test exception và các nhánh guard đặc thù.

## 10. Tự kiểm tra lỗi release bằng compiler

### A. Thử build Java 21 source như Java 17

Khi đã có JDK 21+, chạy:

```bash
javac --release 17 -encoding UTF-8 Java21PatternCompatibilityDemo.java
```

**Kết quả dự kiến: compile thất bại**, vì source dùng Java 21 pattern switch/record patterns không thuộc Java 17 chuẩn. Diagnostic cụ thể tùy compiler; không cần dự đoán chính xác từng câu thông báo lỗi.

Không “sửa” lỗi bằng việc bỏ `--release 17` nếu sản phẩm vẫn cam kết chạy Java 17. Cần dùng cú pháp tương thích Java 17 như chương trình A hoặc **chính thức nâng minimum supported JDK**.

### B. JDK 17 không có compiler target 21

Nếu lệnh `javac` thật sự đến từ JDK 17:

```bash
javac --release 21 Java21PatternCompatibilityDemo.java
```

compiler không hỗ trợ release 21. Muốn dùng source target 21 phải chọn JDK 21+ phù hợp.

### C. Chạy class target 21 trên JVM 17

Class target 21 có major version 65; JVM 17 chỉ hỗ trợ đến major version 61. Khi load class mới, thường gặp `UnsupportedClassVersionError`. Hạ runtime target chỉ khả thi bằng build/cấu trúc source phù hợp, không bằng sửa chuỗi tên JAR.

### D. API có thể sai ngay cả khi syntax cũ

Cú pháp Java 17 không cấm việc vô tình dùng một Java SE API chỉ tồn tại ở bản sau nếu build dùng compiler JDK mới và không giới hạn platform API. `--release 17` giúp ngăn sai sót này. Nhưng dependency bên thứ ba vẫn phải kiểm thử riêng.

## 11. Cấu hình Maven

Trong `pom.xml` của project dùng Maven Compiler Plugin tương thích:

**Chỉ build target Java 17:**

```xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
```

**Chỉ build target Java 21:**

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

Chọn đúng **một cấu hình** cho một artifact, hoặc cấu hình theo từng module có chủ đích. Không đặt Java 21 syntax trong module target 17 rồi kỳ vọng Maven Compiler Plugin tự chuyển đổi.

Kiểm tra:

```bash
mvn -version
mvn -q test
```

`mvn -version` chỉ ra JVM chạy Maven. Nếu project dùng toolchains hoặc compiler fork, compiler thực tế có thể khác; xem log và effective plugin configuration. Test plugin/annotation processor cũng phải hỗ trợ bytecode/runtime đã chọn.

Nếu dùng preview thật, compiler, test runner và runtime phải có flags tương ứng. **Không thêm preview flags vào Java 21 chỉ để dùng record patterns đã final.**

## 12. Cấu hình Gradle và Java toolchains

Ví dụ Gradle **Groovy DSL**:

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

Toolchain chọn Java compiler phù hợp theo hỗ trợ của Gradle; `options.release` ràng buộc source/class/API Java SE target. Nếu target Java 17, đổi cả release và toolchain thành 17, **đồng thời** sửa source để không dùng Java 21 patterns.

Kiểm tra:

```bash
./gradlew --version
./gradlew test
```

Trên Windows có thể dùng `gradlew.bat`, tùy shell. Dùng Gradle Wrapper của dự án để tránh một thành viên vô tình build bằng Gradle không tương thích với JDK mới. Phải phân biệt JVM chạy daemon với toolchain dùng cho compile/test.

**Không giả định rằng công cụ build bất kỳ đều hỗ trợ mọi JDK mới**: kiểm tra phiên bản Gradle, compiler plugin, code generation, annotation processor và test framework trong hệ thống thật.

## 13. IDE, CI, container và dependency compatibility

| Nơi | Kiểm tra | Dấu hiệu sai |
| --- | --- | --- |
| IDE | Project SDK, module language level | IDE cho viết syntax 21 nhưng build target 17 |
| Terminal | `java -version`, `javac -version` | PATH/JAVA_HOME chọn nhầm JDK |
| Maven | Release, toolchain, compiler/test plugins | IDE xanh nhưng Maven fail |
| Gradle | Wrapper, toolchain, options.release, test JVM | Daemon và toolchain khác |
| CI | JDK image, test matrix, cache | CI dùng 17 cho nguồn 21 |
| Docker build | Build-stage JDK | Image build khác local |
| Docker runtime | Runtime JVM khởi chạy artifact | JRE 17 load class 65 |
| Framework | Bytecode instrumentation, reflection, proxies | Lỗi runtime dù javac thành công |
| Annotation processors | Hỗ trợ ngôn ngữ/class-file version | Code generation fail sau upgrade |
| Library consumers | Minimum supported JDK | Khách hàng chưa thể nâng JVM |
| Native/integrations | JVM flags, architecture, JNI, test containers | Integration fail ở môi trường triển khai |

**Quy tắc:** kiểm tra artifact trên **runtime thấp nhất đã công bố**. Nếu artifact target 17 và hỗ trợ cả 17/21, chạy tests trên JVM 17 và JVM 21. Nếu artifact target 21, chạy tests trên 21 và các JVM mới hơn nằm trong hợp đồng hỗ trợ, không đòi artifact ấy chạy ngược trên 17.

Một Dockerfile multi-stage dùng JDK 21 để build nhưng JRE 17 để chạy là một lỗi compatibility có thể đoán trước. Với dự án thực tế, ưu tiên base images và digest đã được tổ chức kiểm chứng; đừng đoán version từ tên tag không kiểm tra.

### Kiểm tra runtime/class files trong build pipeline

Một pipeline tốt cần có:
- Một bước in `java -version` và compiler/toolchain version;
- Clean compile theo `--release`;
- Unit tests trên baseline;
- Integration tests cho framework/dependency quan trọng;
- Smoke test startup trên image thật;
- Kiểm tra lỗi load class và API khi chạy;
- Regression tests cho null, pattern fail, guard false, dominance/exhaustiveness.

Không cần log toàn bộ payload nghiệp vụ chỉ để xác định branch nào được chọn. Dùng Case ID và dữ liệu kiểm thử giả lập phù hợp.

## 14. Bảng quyết định chọn cú pháp theo phiên bản

| Bài toán | Nếu target 17 | Nếu target 21 |
| --- | --- | --- |
| Kiểm tra kiểu Object | `instanceof Type t` | `instanceof Type t` hoặc pattern switch |
| Deconstruct record | Gọi accessor trên record sau type check | Có thể dùng `Record(var x, var y)` |
| Phân loại nhiều subtype sealed | `if/instanceof` hoặc polymorphism | Exhaustive `switch` patterns |
| Guard theo nội dung String | `if (value instanceof String s && condition)` | `case String s when condition` |
| Selector null | Chặn trước hoặc xử lý riêng | `case null` phù hợp hoặc chặn trước |
| Nested dữ liệu nhiều tầng | Type check rồi gọi accessor | Nested record patterns khi thật sự cần |
| Thêm subtype | Review `if`, tests | Compiler có thể nhắc cập nhật exhaustive switch |
| Không muốn preview | Tránh switch patterns preview | Dùng JEP 440/441 final không flags |

**Không nên migrate chỉ vì cú pháp ngắn hơn.** Nếu `if/instanceof` đã rõ, hoặc chính sách cần I/O/side effects phức tạp, một helper/domain method có tên rõ có thể tốt hơn một `switch` lớn. Compatibility chỉ là một trong các tiêu chí; tính dễ đọc và behavior phải được giữ.

## 15. Semantics cần kiểm tra khi chuyển lên Java 21

### Pattern variable và phạm vi

`instanceof String s` (Java 16+) ràng buộc biến `s` khi compiler biết pattern khớp. Trong `if` với `&&`, biến pattern có thể được dùng ở vế phải nơi pattern thành công:

```java
if (value instanceof String s && !s.isBlank()) {
    System.out.println(s.strip());
}
```

Không coi `s` là một biến có scope ở mọi nhánh hoặc sau khi control-flow không bảo đảm pattern.

### Nested record null

```java
record Address(String city) {}
record Ship(Address address) {}

// Java 21:
if (value instanceof Ship(Address(var city))) {
    // Ship và Address đã khớp kiểu non-null;
    // city vẫn có thể null.
}
```

`new Ship(null)` không khớp nested pattern. `new Ship(new Address(null))` có thể khớp, vì `var city` nhận component null. Guard `when city != null` chỉ được xét **sau** matching thành công.

### Pattern guard vs runtime exception

Guard `when` trả false thì switch có thể xét case tiếp theo. Nhưng nếu guard ném exception thì không thể xem nó như false. Tương tự, accessor tùy biến của record có thể ném exception trong deconstruction; Java 21 có quy tắc `MatchException` với cause gốc. Đừng coi mọi exception trong quá trình matching là “pattern không khớp”.

### Thứ tự case và dominance

```java
// CỐ Ý SAI VỀ THỨ TỰ:
case String s -> "ANY";
case String s when s.isBlank() -> "BLANK";
```

Case String tổng quát che nhánh guard; Java 21 compiler có thể báo dominance. Đặt case cụ thể trước case rộng. Với sealed hierarchy, tránh `default` che việc chưa xử lý subtype mới nếu compiler có thể giúp kiểm tra exhaustive.

### Null selector trong switch

Đừng mặc định `default` của enhanced `switch` nhận selector null. Trong Java 21, dùng `case null` khi null là một trạng thái hợp lệ, hoặc từ chối null bằng `Objects.requireNonNull` trước switch khi contract cấm.

## 16. Checklist review trước khi release

| Kiểm tra | Câu hỏi cụ thể | Dấu hiệu đạt |
| --- | --- | --- |
| Phiên bản hỗ trợ | JVM tối thiểu là 17, 21 hay khác? | Có trong tài liệu |
| Nhóm tính năng | `instanceof`, records, sealed, pattern switch, record patterns? | Đối chiếu mốc final |
| Preview | Feature có final ở baseline không? | Không bật preview nếu không cần |
| Syntax | Có `when`, nested record, `_`? | Hợp lệ với target |
| Compiler | JDK biên dịch hỗ trợ `--release`? | Phiên bản được xác nhận |
| Class file | Target <= runtime thấp nhất? | Không có lỗi class version |
| API platform | Build giới hạn Java SE APIs? | `--release` phù hợp |
| Dependencies | Library/framework đọc được bytecode? | Integration tests PASS |
| Build plugins | Maven/Gradle/processor hỗ trợ JDK? | CI clean build PASS |
| Test runner | Test JVM đúng phiên bản? | Ma trận rõ |
| Null selector | Có contract và test? | Không phụ thuộc default mơ hồ |
| Null component | Record con null khác `var` null? | Đã test |
| Guard | Đúng thứ tự, thuần, null-safe? | Không side effect bất ngờ |
| Dominance | Case cụ thể trước case tổng quát? | Compile PASS |
| Exhaustiveness | Sealed variants đủ nhánh? | Không dùng default che thiếu |
| Migration | Output/exception/side effects giữ nguyên? | Regression tests PASS |
| Docker/server | JVM thật tương thích artifact? | Smoke test PASS |
| Tài liệu | Minimum Java đã cập nhật? | Release notes/README chính xác |

Với thư viện phát hành rộng, ghi thêm các thông tin như ABI/API compatibility, module path/classpath và test trên những JVM do sản phẩm cam kết hỗ trợ. Với ứng dụng đóng chỉ chạy một Docker image, tập trung kiểm chứng image thật và cơ chế upgrade/rollback.

## 17. Quy trình migration Java 17 → Java 21

1. **Chốt baseline:** xác định nơi nào vẫn chạy Java 17, ai sở hữu môi trường và có thể nâng lên 21 hay không.
2. **Đánh giá dependencies:** framework, plugins, instrumentation, annotation processors, JVM flags và image runtime.
3. **Nâng toolchain/build:** JDK 21+, `--release 21`, không preview cho pattern switch/record patterns final.
4. **Chạy regression trước refactor:** tạo bộ input với các subtype, guard true/false, nested null và exception.
5. **Refactor từng chỗ:** chuyển `if/instanceof` sang pattern switch khi thật sự tăng tính rõ ràng.
6. **Giữ chính sách nghiệp vụ:** không tiện tay thay đổi validation, ordering, null contract hoặc side effects cùng lúc.
7. **Kiểm tra compiler:** fix dominance/exhaustiveness đúng nguyên nhân, không thêm default tùy tiện.
8. **Chạy unit/integration tests:** đặc biệt logic dùng sealed hierarchy và record deconstruction.
9. **Kiểm tra deployment:** chạy artifact trên runtime Docker/server Java 21 được chốt.
10. **Công bố thay đổi:** cập nhật minimum Java requirement, release notes và hướng dẫn người sử dụng.

Nếu sản phẩm vẫn **phải hỗ trợ Java 17**, không thể hoàn thành migration bằng cách chuyển mọi source sang syntax Java 21 trong artifact chung. Có thể giữ module Java 17 hoặc chia ranh giới module/deployment rõ ràng.

## 18. Lỗi phổ biến

| Hiểu lầm | Rủi ro | Cách sửa |
| --- | --- | --- |
| “Switch `->` có từ 14 nên pattern switch từ 14” | Compile fail | Phân biệt JEP 361 với JEP 441 |
| “Record từ 16 nên record pattern từ 16” | Compile fail | Record patterns final 21 |
| “Sealed từ 17 nên switch có type patterns từ 17” | Nhầm preview | Pattern switch final 21 |
| “Preview flag mở mọi syntax tương lai” | Không tương thích | Chỉ dùng feature preview đúng JDK |
| “JDK 21 ở máy nên server 17 vẫn chạy” | `UnsupportedClassVersionError` | Nâng runtime hoặc hạ source/target thật |
| “Chỉ `-target 17` là đủ” | Có thể gọi APIs mới | `--release 17` + test JVM 17 |
| “`_` luôn dùng được trong Java 21” | Syntax không hỗ trợ | Unnamed patterns final Java 22 |
| “`default` tự nhận selector null” | Null handling sai | `case null` hoặc chặn trước |
| “Guard false tức nhánh đã chạy” | Debug/metrics sai | Theo dõi case được chọn |
| “Nested Address null vẫn vào `when`” | Guard không chạy | Hiểu structural matching |
| “Đảo case không ảnh hưởng” | Dominance / logic sai | Nhánh cụ thể trước |
| “Thêm subtype sealed không cần sửa switch” | Bỏ sót nghiệp vụ | Exhaustive switch + tests |
| “Một lần chạy local chứng minh compatibility” | CI/prod khác JDK | Chạy trên runtime thấp nhất |
| “Framework cũ luôn đọc class 65” | Bytecode parser fail | Nâng/test dependency |
| “Đổi syntax luôn giữ hành vi” | Null/exception/side effect khác | Regression test |
| “LTS nghĩa là mọi vendor hỗ trợ vô hạn” | Sai chính sách support | Kiểm tra vendor và lịch bảo trì |

## 19. Bài tập thực hành

**Bài 1 — Tra mốc.** Xác định version final đầu tiên của `switch expression`, `instanceof String s`, `record`, `sealed`, `case String s when ...` và `Point(var x,var y)`. Đáp án: **14, 16, 16, 17, 21, 21**.

**Bài 2 — Build hai chương trình.** Biên dịch `Java17FallbackDemo.java` bằng `--release 17` và `Java21PatternCompatibilityDemo.java` bằng `--release 21` trên compiler phù hợp. Chạy cả hai trên JVM 21 và so sánh stdout.

**Bài 3 — Hạ release.** Thử `javac --release 17 Java21PatternCompatibilityDemo.java`. Giải thích vì sao compile fail dù máy cài JDK 21. Không dùng preview như một cách hạ target.

**Bài 4 — Guard/dominance.** Đổi thứ tự hai nhánh Create trong Java 21 program. Quan sát compiler và khôi phục nhánh guard trước.

**Bài 5 — Hai loại null.** Với `Ship("O-5", null)` và `Ship("O-6", new Address(null))`, mô tả vì sao một input **pattern fail**, input còn lại **guard false**.

**Bài 6 — Thêm subtype.** Tạo `Refund implements Action` và cập nhật `permits`. Tại sao Java 21 switch expression nhắc thiếu case, còn Java 17 chain `if` chỉ có fallback runtime?

**Bài 7 — Gradle/Maven.** Chọn min runtime 17 và viết config release 17. Nếu source dùng Java 21 record patterns, cần thay đổi code hay đổi cam kết runtime?

**Bài 8 — Preview.** Tìm một ví dụ JDK 19 record pattern preview. Vì sao không thể kết luận nó chạy mặc định trên Java 19 không preview? Khi port lên Java 21, cần kiểm tra syntax và tests gì?

**Bài 9 — CI và Docker.** IDE JDK 21, CI JDK 17, runtime Docker JRE 17. Những thành phần nào cần nâng nếu code target 21? Thay Project SDK trong IDE có đủ không?

**Bài 10 — Thư viện public.** Nếu khách hàng vẫn dùng JVM 17, có thể phát hành JAR target 21 cho họ không? Nêu cách giữ artifact tương thích 17.

**Bài 11 — Platform API.** Giải thích vì sao `-source 17 -target 17` trên JDK mới chưa ràng buộc đầy đủ API Java SE 17, và lợi ích của `--release 17`.

**Bài 12 — Migration regression.** Lập ma trận test cho Create quantity 0/1, Ship address null/city null/blank/đúng, selector null và subtype mới. Nên so output, branch ID, exception hay side effects?

## 20. Ghi nhớ

**Checklist tương thích phiên bản Java Pattern Matching** cần làm theo thứ tự:

1. Xác định JVM thấp nhất sản phẩm thật sự phải chạy.
2. Tra **mốc final** của từng syntax, không nhầm preview với tính năng mặc định.
3. Chọn compiler và `--release` phù hợp; kiểm tra class-file/API target.
4. Đồng bộ Maven/Gradle/CI và image runtime; test dependency/framework.
5. Kiểm tra semantics của null, guard, dominance, exhaustiveness, record deconstruction và exception.
6. Dùng regression tests khi nâng từ Java 17 sang 21, không chỉ dựa vào compile success.
7. Công bố minimum Java version rõ ràng và cập nhật khi nâng baseline.

**Mốc cốt lõi:** Java **14** có switch expressions; Java **16** có records và pattern `instanceof`; Java **17** có sealed types; Java **21** có pattern switch/`when`/record patterns final; Java **22** có unnamed patterns/variables final.

### Tài liệu tham khảo

- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 406 — Pattern Matching for switch (First Preview)](https://openjdk.org/jeps/406)
- [JEP 420 — Pattern Matching for switch (Second Preview)](https://openjdk.org/jeps/420)
- [JEP 427 — Pattern Matching for switch (Third Preview)](https://openjdk.org/jeps/427)
- [JEP 433 — Pattern Matching for switch (Fourth Preview)](https://openjdk.org/jeps/433)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 405 — Record Patterns (Preview)](https://openjdk.org/jeps/405)
- [JEP 432 — Record Patterns (Second Preview)](https://openjdk.org/jeps/432)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 456 — Unnamed Variables & Patterns](https://openjdk.org/jeps/456)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [Oracle Java 21 — javac options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
