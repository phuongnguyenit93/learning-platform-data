# Property-based test cho pattern trong Java 21+

## 1. Property-based testing kiểm thử điều gì?

**Property-based testing (PBT)** là phương pháp viết **tính chất phải đúng cho một tập lớn đầu vào**, sau đó để bộ sinh dữ liệu tạo nhiều trường hợp nhằm tìm **phản ví dụ (counterexample)**. Thay vì chỉ kiểm tra ba ví dụ cố định, ta phát biểu những mệnh đề như:

- Với mọi `Parcel` có kiểu hợp lệ, hàm phân loại bằng pattern phải đồng ý với đặc tả độc lập của nghiệp vụ.
- Thay đổi mã theo dõi (`trackingId`) không được làm đổi hạng vận chuyển nếu hạng chỉ phụ thuộc vào trọng lượng và thông tin điểm đến hợp lệ.
- Với điểm đến hợp lệ, kiện nặng đúng **5.000 g** vẫn thuộc nhóm `STANDARD`; từ **5.001 g** mới thành `HEAVY`.
- Với selector hoặc record component `null`, kết quả phải đúng chính sách đã định; không được âm thầm rơi vào `MatchException` ngoài ý muốn.
- Việc thêm một subtype vào sealed hierarchy không được tạo ra trạng thái xử lý thiếu mà test không phát hiện.

Đây là cách kiểm thử đặc biệt phù hợp với **pattern matching** bởi kết quả phụ thuộc đồng thời vào:

1. **Kiểu và cấu trúc**: `String`, `Integer`, sealed subtype, record và nested record pattern.
2. **Ràng buộc trong pattern**: các component nào được deconstruct, giá trị nào có thể `null`.
3. **Guard `when`**: biểu thức Boolean, biên `>`/`>=`, thứ tự đánh giá ngắn mạch.
4. **Thứ tự nhánh `switch`**: pattern cụ thể, guard và nhánh dự phòng.
5. **Tính exhaustive và thay đổi domain**: toàn bộ subtype đã được xét hay chưa.

**Không nên nhầm PBT với random smoke test.** Một bài test chỉ sinh dữ liệu rồi gọi method mà không có mệnh đề kiểm tra đúng/sai chưa phải PBT hữu ích. Tính chất phải độc lập và có ý nghĩa nghiệp vụ.

**Phiên bản Java:** Record patterns (JEP 440) và pattern matching for `switch` (JEP 441) chính thức trong **Java 21**. Mã minh họa chạy với JDK 21+, không cần `--enable-preview`. Phần chạy bằng `java.util.Random` không cần framework ngoài; phần cuối giới thiệu cách viết property thực sự bằng **jqwik** trên JUnit Platform, có khả năng shrinking.

## 2. Chuyển quy tắc domain thành các properties

Giả sử hệ thống phân loại kiện hàng:

```java
sealed interface Parcel permits Physical, Digital, Unknown {}
record City(String name) {}
record Physical(String trackingId, City city, int grams)
        implements Parcel {}
record Digital(String trackingId, String email)
        implements Parcel {}
record Unknown() implements Parcel {}
```

Hợp đồng nghiệp vụ:

| Kiểu / đầu vào | Quy tắc | Kết quả |
| --- | --- | --- |
| `Physical` | City tồn tại, tên không `null`/blank, `grams > 5_000` | `HEAVY` |
| `Physical` | City tồn tại, tên không `null`/blank, `1 <= grams <= 5_000` | `STANDARD` |
| `Physical` | City không hợp lệ hoặc `grams <= 0` | `INVALID_PHYSICAL` |
| `Digital` | Email khác `null` và có dấu `@` (quy tắc đơn giản của ví dụ) | `DIGITAL` |
| `Digital` | Email thiếu dấu `@` hoặc null | `INVALID_DIGITAL` |
| `Unknown` | Không có quy tắc riêng | `UNKNOWN` |
| Selector null | Không có kiện hàng | `MISSING` |

*Lưu ý:* quy tắc kiểm tra email bằng `contains("@")` chỉ là một giả định minh họa, **không phải email validator hoàn chỉnh**. Bài test nên dùng đúng **hợp đồng domain được công bố**, không tự coi quy tắc demo là chuẩn chung.

Từ bảng trên, tạo một bộ properties theo các cấp độ độc lập:

- **Oracle / differential property:** `classify(parcel) == reference(parcel)` trên tất cả giá trị được sinh, trong đó `reference` là cách triển khai độc lập dễ đọc từ hợp đồng.
- **Boundary property:** chính xác 5.000 g là `STANDARD`, 5.001 g là `HEAVY`; trọng lượng 0 hoặc âm là không hợp lệ.
- **Metamorphic property:** thay đổi `trackingId` (và một tên City hợp lệ sang tên City hợp lệ khác) không làm thay đổi hạng khi trọng lượng không đổi.
- **Null/shape property:** `Physical(null-city)`, `Physical(City(null))` và `Physical(City(" "))` đi vào nhánh `INVALID_PHYSICAL`; selector null đi vào `MISSING`.
- **No-unexpected-exception property:** với những đầu vào thuộc miền mà hợp đồng cho phép, `classify` không được ném ngoại lệ bất ngờ.

Không cần viết mọi property thành một phép so sánh output y hệt switch. Các mệnh đề metamorphic, invariants và boundary giúp tìm lỗi **ngay cả khi oracle có cùng sai sót với implementation**.

## 3. Bộ sinh dữ liệu cần biết các nhánh pattern

Sinh ngẫu nhiên đồng đều trên mọi `int` thường bỏ lỡ giá trị cần test nhất: **0, 1, 5.000 và 5.001**. Tương tự, sinh ký tự ngẫu nhiên có thể hiếm khi tạo ra null, chuỗi rỗng hay blank.

Với `Parcel`, nên sinh theo **cấu trúc trước, giá trị sau**:

1. Chọn một trường hợp: selector null, `Physical`, `Digital` hoặc `Unknown`.
2. Nếu `Physical`, quyết định có tạo `City` hay không; nếu có, chọn `City.name` từ null, rỗng, blank và tên hợp lệ.
3. Sinh `grams` bằng hỗn hợp: bộ **boundary values** `-1, 0, 1, 4_999, 5_000, 5_001`, giá trị cực trị và số ngẫu nhiên trong một khoảng đại diện.
4. Nếu `Digital`, sinh email null, rỗng, thiếu `@` hoặc có `@`.
5. Đảm bảo có thể tái hiện lần sinh gây lỗi bằng **seed**, và khi dùng framework PBT thì tận dụng **shrinking** để rút gọn input lỗi.

**Vì sao cần trọng số cho từng loại?** Một bộ sinh chọn theo phân phối không phù hợp có thể tạo 99% `Unknown`, khiến nhánh guard của `Physical` hầu như không được kiểm thử. Cần theo dõi phân phối (classification statistics) và điều chỉnh generator để các nhánh quan trọng được gặp đủ thường xuyên.

**Hợp lệ và không hợp lệ đều quan trọng:** Nếu domain cấm City null ở constructor, generator của test đường đi hợp lệ không nên tạo trạng thái đó. Nhưng test API nhận dữ liệu chưa được validate hoặc deserialization vẫn cần các input xấu ở **biên hệ thống**. Phân biệt rõ hai tập dữ liệu để test không tự mâu thuẫn với invariant của model.

## 4. Chương trình hoàn chỉnh, chạy được bằng Java 21

Chương trình sau kiểm thử bằng ba lớp: **12 boundary examples**, **20.000 input sinh ngẫu nhiên so sánh với oracle** và **5.000 phép kiểm tra metamorphic**. Không cần thư viện ngoài.

Lưu file tên **`ParcelPatternPropertyDemo.java`**:

```java
public class ParcelPatternPropertyDemo {
    sealed interface Parcel permits Physical, Digital, Unknown {}

    record City(String name) {}

    record Physical(String trackingId, City city, int grams)
            implements Parcel {}

    record Digital(String trackingId, String email)
            implements Parcel {}

    record Unknown() implements Parcel {}

    // Hệ thống cần kiểm thử: nested record pattern + when guards.
    static String classify(Parcel parcel) {
        return switch (parcel) {
            case Physical(var id, City(String city), int grams)
                    when grams > 5_000
                            && city != null && !city.isBlank() ->
                    "HEAVY";

            case Physical(var id, City(String city), int grams)
                    when grams > 0
                            && city != null && !city.isBlank() ->
                    "STANDARD";

            case Physical(var id, var city, var grams) ->
                    "INVALID_PHYSICAL";

            case Digital(var id, var email)
                    when email != null && email.contains("@") ->
                    "DIGITAL";

            case Digital(var id, var email) ->
                    "INVALID_DIGITAL";

            case Unknown unknown -> "UNKNOWN";
            case null -> "MISSING";
        };
    }

    // Oracle độc lập: không dùng nested record patterns/when.
    // Viết theo bảng hợp đồng để có đường kiểm chứng thứ hai.
    static String reference(Parcel parcel) {
        if (parcel == null) {
            return "MISSING";
        }

        if (parcel instanceof Physical physical) {
            City city = physical.city();

            if (city == null || city.name() == null ||
                    city.name().isBlank() || physical.grams() <= 0) {
                return "INVALID_PHYSICAL";
            }

            return physical.grams() > 5_000
                    ? "HEAVY" : "STANDARD";
        }

        if (parcel instanceof Digital digital) {
            return digital.email() != null
                    && digital.email().contains("@")
                            ? "DIGITAL" : "INVALID_DIGITAL";
        }

        if (parcel instanceof Unknown) {
            return "UNKNOWN";
        }

        throw new AssertionError("Unknown Parcel implementation");
    }

    static void assertEqual(
            String expected, String actual, Object value) {
        if (!java.util.Objects.equals(expected, actual)) {
            throw new AssertionError(
                    "value=" + value + " expected=" + expected
                            + " actual=" + actual);
        }
    }

    // Generator có thiên hướng sinh các kiểu và giá trị biên.
    static Parcel generate(java.util.Random random) {
        String[] cities = {
                null, "", " ", "HCM", "Huế", "Hà Nội"
        };

        String[] emails = {
                null, "", "no-at-sign", "a@b", "person@example.com"
        };

        int[] edges = {
                -1, 0, 1, 4_999, 5_000, 5_001,
                Integer.MIN_VALUE, Integer.MAX_VALUE
        };

        int grams = random.nextBoolean()
                ? edges[random.nextInt(edges.length)]
                : random.nextInt(20_001) - 10_000;

        String id = "P" + random.nextInt(100);

        return switch (random.nextInt(6)) {
            case 0 -> null;

            case 1, 2, 3 -> new Physical(
                    id,
                    random.nextInt(5) == 0
                            ? null
                            : new City(
                                    cities[random.nextInt(cities.length)]),
                    grams);

            case 4 -> new Digital(
                    id,
                    emails[random.nextInt(emails.length)]);

            default -> new Unknown();
        };
    }

    public static void main(String[] args) {
        Parcel[] boundaries = {
                new Physical("A", new City("HCM"), 5_000),
                new Physical("A", new City("HCM"), 5_001),
                new Physical("A", new City("HCM"), 1),
                new Physical("A", new City("HCM"), 0),
                new Physical("A", new City("HCM"), -1),
                new Physical("A", null, 10),
                new Physical("A", new City(null), 10),
                new Physical("A", new City(" "), 10),
                new Digital("D", "a@b"),
                new Digital("D", null),
                new Unknown(),
                null
        };

        String[] expected = {
                "STANDARD", "HEAVY", "STANDARD",
                "INVALID_PHYSICAL", "INVALID_PHYSICAL",
                "INVALID_PHYSICAL", "INVALID_PHYSICAL",
                "INVALID_PHYSICAL", "DIGITAL",
                "INVALID_DIGITAL", "UNKNOWN", "MISSING"
        };

        for (int i = 0; i < boundaries.length; i++) {
            assertEqual(
                    expected[i], classify(boundaries[i]), boundaries[i]);
        }
        System.out.println("boundaries=12 PASS");

        final long seed = 24_301L;
        java.util.Random random = new java.util.Random(seed);

        for (int i = 0; i < 20_000; i++) {
            Parcel input = generate(random);
            assertEqual(reference(input), classify(input), input);
        }
        System.out.println(
                "differential=20000 PASS (seed=" + seed + ")");

        // Metamorphic: trackingId và tên City hợp lệ không
        // thay đổi hạng đối với cùng trọng lượng dương.
        java.util.Random metamorphicRandom =
                new java.util.Random(seed + 1);

        for (int i = 0; i < 5_000; i++) {
            int grams = 1 + metamorphicRandom.nextInt(10_000);
            Parcel original = new Physical(
                    "ID-A", new City("HCM"), grams);
            Parcel renamed = new Physical(
                    "ID-B", new City("Huế"), grams);

            assertEqual(
                    classify(original), classify(renamed), renamed);
        }
        System.out.println("metamorphic=5000 PASS");
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 ParcelPatternPropertyDemo.java
java ParcelPatternPropertyDemo
```

**Stdout chính xác:**

```text
boundaries=12 PASS
differential=20000 PASS (seed=24301)
metamorphic=5000 PASS
```

Chương trình đã được kiểm tra với JDK 24 theo cú pháp Java 21. Phần này dùng **randomized property checks tự viết** để có ví dụ chạy bằng JDK thuần. Nó **không tự động shrink** phản ví dụ; framework chuyên dụng như jqwik sẽ cung cấp cơ chế đó.

### 4.1. Giải thích nhánh record lồng và dữ liệu null

Hai nhánh đầu dùng:

```java
case Physical(var id, City(String city), int grams)
        when grams > 5_000 && city != null && !city.isBlank() ->
        "HEAVY";
```

`City(String city)` chỉ khớp khi component `City` thực sự là một record `City`, **không khớp khi chính `City` là null**. Nhưng `City` có thể tồn tại và chứa `name == null`; guard kiểm tra `city != null` giúp xử lý trường hợp đó.

Nhánh thứ ba:

```java
case Physical(var id, var city, var grams) -> "INVALID_PHYSICAL";
```

là nhánh dự phòng cho `Physical` không qua hai guard phía trên, bao gồm City null, City rỗng và trọng lượng không dương. Nhánh này được đặt **sau** nhánh cụ thể; nếu đặt trước, nó sẽ bao phủ các `Physical` khác và làm các nhánh trên bị dominated.

### 4.2. Vì sao có cả test ví dụ cố định lẫn test ngẫu nhiên?

Property-based testing **bổ sung**, không thay thế kiểm thử ví dụ. Các ca cố định chứng minh ranh giới quan trọng đã được khẳng định rõ (5.000/5.001, null ở từng tầng) ngay cả nếu generator tình cờ không sinh chúng. Vòng ngẫu nhiên khám phá thêm các kết hợp mà người viết chưa liệt kê; property metamorphic bắt loại hồi quy khác với đơn thuần so sánh output bằng oracle.

`seed = 24301` tái hiện **chính xác chuỗi sinh của code này** khi generator và cách gọi ngẫu nhiên không đổi. Nếu sửa generator hoặc version thuật toán sinh, cùng seed không nhất thiết tạo cùng input sequence. Khi phát hiện bug, hãy lưu **giá trị phản ví dụ cụ thể** và chuyển nó thành regression test cố định.

## 5. Một framework PBT thực sự: jqwik

Trong dự án Maven/Gradle, **jqwik** cung cấp các khái niệm:

- `@Property`: đánh dấu một property test, cấu hình số lần thử.
- `@ForAll`: tham số được sinh tự động.
- `@Provide` và `Arbitrary<T>`: mô tả bộ sinh domain.
- `Arbitraries.oneOf(...)`: kết hợp generator trường hợp biên và phân phối ngẫu nhiên.
- **Shrinking:** sau khi thấy input thất bại, jqwik thường tìm phiên bản **đơn giản hơn** mà vẫn làm property sai (khả năng và chất lượng shrink phụ thuộc generator).

Một dependency Maven mẫu (có thể dùng version tương thích theo [jqwik User Guide](https://jqwik.net/docs/current/user-guide); dưới đây minh họa bản `1.10.2`):

```xml
<dependency>
    <groupId>net.jqwik</groupId>
    <artifactId>jqwik</artifactId>
    <version>1.10.2</version>
    <scope>test</scope>
</dependency>
```

Dự án cần chạy test bằng **JUnit Platform**, ví dụ Maven Surefire bản hiện đại, cấu hình biên dịch Java 21. Đặt file sản phẩm tại `src/main/java/ParcelPatternPropertyDemo.java` và file property test tại `src/test/java/ParcelPatternProperties.java`; cả hai trong cùng package (hoặc cùng default package cho ví dụ đơn giản). Trong dự án thật nên đặt package có tên tường minh.

Ví dụ test sử dụng jqwik:

```java
import net.jqwik.api.*;
import net.jqwik.api.constraints.IntRange;

class ParcelPatternProperties {

    @Provide
    Arbitrary<Integer> gramsNearBoundary() {
        return Arbitraries.oneOf(
                Arbitraries.of(
                        -1, 0, 1, 4_999, 5_000, 5_001,
                        Integer.MIN_VALUE, Integer.MAX_VALUE),
                Arbitraries.integers().between(-10_000, 10_000));
    }

    @Property(tries = 1_000)
    void resultMatchesReference(
            @ForAll("gramsNearBoundary") int grams) {
        var parcel = new ParcelPatternPropertyDemo.Physical(
                "A", new ParcelPatternPropertyDemo.City("HCM"), grams);

        String expected = ParcelPatternPropertyDemo.reference(parcel);
        String actual = ParcelPatternPropertyDemo.classify(parcel);

        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "grams=" + grams
                            + " expected=" + expected
                            + " actual=" + actual);
        }
    }

    @Property(tries = 500)
    void changingIdAndValidCityDoesNotChangeCategory(
            @ForAll @IntRange(min = 1, max = 10_000) int grams) {
        var first = new ParcelPatternPropertyDemo.Physical(
                "A", new ParcelPatternPropertyDemo.City("HCM"), grams);
        var second = new ParcelPatternPropertyDemo.Physical(
                "B", new ParcelPatternPropertyDemo.City("Huế"), grams);

        String x = ParcelPatternPropertyDemo.classify(first);
        String y = ParcelPatternPropertyDemo.classify(second);

        if (!x.equals(y)) {
            throw new AssertionError("grams=" + grams
                    + " first=" + x + " second=" + y);
        }
    }
}
```

Chạy theo cấu hình dự án:

```bash
mvn test
```

Đây là phần **ví dụ tích hợp framework**; đoạn chương trình `ParcelPatternPropertyDemo.java` ở mục 4 đã được thực thi độc lập bằng JDK. Đoạn jqwik sử dụng các API theo tài liệu hướng dẫn, nhưng yêu cầu dự án có dependency và cấu hình chạy test tương ứng.

**Giới hạn của test jqwik trên:** hai properties tập trung vào `Physical` với City hợp lệ. **Chúng chưa kiểm tra tất cả subtype/null**, nên cần thêm `@Provide` cho `Parcel` để sinh được `Digital`, `Unknown`, selector null, City null và tên City null/blank. Không được tuyên bố “đã property-test toàn bộ switch” chỉ vì hai properties chạy qua.

### 5.1. Thiết kế `Arbitrary<Parcel>` theo sealed hierarchy

Chiến lược có thể triển khai:

- `physicalArbitrary()` kết hợp `trackingId`, `City` và `grams` bằng `Combinators.combine(...).as(...)`.
- `digitalArbitrary()` kết hợp identifier và email hợp lệ/bất hợp lệ.
- `unknownArbitrary()` dùng `Arbitraries.just(new Unknown())`.
- `parcelArbitrary()` dùng `Arbitraries.oneOf(physical, digital, unknown)` rồi **injectNull** ở tầng selector nếu domain cho phép null.
- Tạo bộ sinh **valid domain** và **invalid input** riêng khi constructor hoặc schema có ràng buộc, tránh lọc quá nhiều bằng `filter(...)`.

Tránh dùng `Arbitraries.randomValue(...)` với generator tự phát mà không biết nhược điểm: theo jqwik, các giá trị tạo theo cách này **không shrink được**. Với dữ liệu record có cấu trúc, ưu tiên composition của các Arbitrary có khả năng shrink để phản ví dụ được thu nhỏ hữu ích.

### 5.2. Shrinking: từ input phức tạp thành ca lỗi tối giản

Giả sử một người thay `grams > 5_000` bằng `grams >= 5_000` ở nhánh `HEAVY`. Khi chạy property:

```java
// Sai nếu hợp đồng nói chỉ > 5_000 mới là HEAVY:
case Physical(var id, City(String city), int grams)
        when grams >= 5_000 && city != null && !city.isBlank() ->
        "HEAVY";
```

Bài test boundary phát hiện trực tiếp input `new Physical("A", new City("HCM"), 5_000)`: đặc tả chờ `STANDARD`, code trả `HEAVY`.

Với generator và framework hỗ trợ shrinking, jqwik **có thể** cố rút input thất bại xuống giá trị đơn giản ở ranh giới. Không hứa chắc nó luôn shrink được thành 5.000; kết quả phụ thuộc generator, thứ tự/số lần thử và các ràng buộc. Khi có phản ví dụ, ghi lại **input cụ thể + seed + version thư viện**, sửa code và thêm regression test cố định.

## 6. Năm dạng property có giá trị cao cho pattern matching

### 6.1. Agreement với oracle độc lập

`classify(input) == reference(input)` có thể nhận ra sai thứ tự guard, thiếu fallback hoặc nhầm ngưỡng. Nhưng **tránh copy lại chính switch sang oracle**: nếu cả hai cùng sao chép một lỗi, test có thể xanh giả. Viết reference theo bảng domain, dạng biểu thức đơn giản hoặc dữ liệu kỳ vọng do bên nghiệp vụ xác nhận.

### 6.2. Metamorphic property

Khi khó biết output chính xác của input ngẫu nhiên, ta vẫn có thể biết một phép biến đổi **không được làm thay đổi kết quả**:

- Đổi identifier không ảnh hưởng tới nhóm vận chuyển.
- Với City hợp lệ, đổi tên từ `HCM` sang `Huế` không ảnh hưởng tới nhóm dựa vào trọng lượng.
- Nếu domain có chuẩn hóa chữ hoa/thường, thay đổi case của input không được làm thay đổi nhóm (chỉ đúng khi hợp đồng thật sự quy định).

Một metamorphic relation cần **precondition** rõ. Nếu City bị đổi thành null hoặc blank, quan hệ “không đổi nhóm” không còn hợp lệ. Việc viết property mà quên precondition sẽ tạo false positive.

### 6.3. No unexpected exception / totality

Với selector và record component thuộc miền cho phép, hàm phân loại nên kết thúc bình thường và trả một trong các nhãn hợp lệ. Nhưng **đừng định nghĩa thuộc tính quá yếu** kiểu “không throw là PASS”: một `default -> "OTHER"` che mọi lỗi cũng sẽ không throw.

Kết hợp property totality với oracle, kiểm tra tập giá trị, và kiểm thử boundary. Đối với sealed hierarchy hoặc nested record pattern, chú ý `MatchException` khi một record con null làm tất cả case exhaustive trượt, hoặc khi client được biên dịch với một tập subtype cũ.

### 6.4. Exhaustiveness, subtype và thứ tự nhánh

Compiler Java 21 giúp kiểm tra tính exhaustive với `sealed`, nhưng test runtime vẫn có giá trị cho:

- Component nullable bên trong record pattern lồng.
- Hai guard cùng có thể đúng, với nhánh cụ thể phải đứng trước.
- Trường hợp subtype con cần ưu tiên hơn type cha.
- Đặc tả có nhánh không guard tiếp nhận phần còn lại.

Khi bổ sung subtype vào sealed hierarchy, trước hết cập nhật generator để **thực sự sinh subtype mới**, rồi kiểm thử classifier. Nếu chỉ thêm case code mà không cập nhật generator, PBT có thể không đụng tới đường đi mới.

### 6.5. Regression property so với triển khai cũ

Nếu chuyển legacy `instanceof + cast` sang `switch` pattern, property:

`newVersion(input) == oldVersion(input)`

có ích khi **hành vi cũ là contract được chấp nhận**. Cần kiểm tra thêm null, exception type, side effect quan trọng, nhất là nếu refactor chuyển từ check getter thủ công sang record deconstruction. Kết quả trả về giống nhau không chứng minh hai phiên bản giống nhau về số lần ghi database, event, log hoặc exception.

Không chạy đồng thời hai biến thể lên hệ thống production nếu chúng có side effect; hãy dùng test cô lập và fake/mock phù hợp.

## 7. Những điều PBT không thể tự bảo đảm

1. **Không chứng minh chương trình đúng cho mọi input.** 20.000 ca kiểm thử là dữ liệu hữu hạn, không phải chứng minh hình thức.
2. **Không tự bảo đảm branch coverage.** Tăng `tries` nhưng generator chỉ tạo `Digital` sẽ không kiểm tra `Physical`.
3. **Không cứu được một oracle sai.** Cần review hợp đồng, test độc lập và đôi khi mutation testing.
4. **Không tự xác định miền dữ liệu hợp lệ.** Generator phải phản ánh invariant/constructor/API.
5. **Không tự động tìm được mọi trạng thái sâu.** Nested records, generic data và sealed subtype cần bộ sinh có cấu trúc.
6. **Không nên bị biến thành kiểm thử không ổn định.** Nguồn I/O, thời gian thực, trạng thái global có thể làm property fail ngẫu nhiên khó tái hiện.
7. **Không thay thế ví dụ đặc tả.** Boundary 0, 1, 5.000, 5.001 nên có test tường minh bên cạnh generator.
8. **Không bảo đảm shrinking luôn tối ưu.** Dữ liệu được sinh bằng phương pháp không shrink được hoặc dùng filter quá mức có thể khiến phản ví dụ khó thu nhỏ.
9. **Không bảo đảm match null an toàn.** Với pattern lồng, null có thể xuất hiện ở nhiều tầng; cần generator và case đúng tầng.

**Vì vậy:** kết hợp **example-based tests + property-based tests + coverage + review đặc tả**. PBT mạnh nhất khi cung cấp một góc nhìn kiểm chứng độc lập.

## 8. Quy trình áp dụng vào codebase

1. **Chọn một method phân loại theo pattern** có hợp đồng rõ: điều kiện subtype, guard, ranh giới, null.
2. **Viết bảng quyết định**: từng loại input, điều kiện, output mong đợi, exception/hành vi fallback.
3. **Tạo các regression examples trước** cho ranh giới và bug từng gặp.
4. **Chọn property**: oracle/differential, metamorphic và invariant phù hợp. Viết mệnh đề bằng tiếng người trước khi mã hóa thành assertion.
5. **Xây generator theo cấu trúc domain**: subtype, nested record, null ở từng tầng, boundary và invalid data nếu API nhận được.
6. **Chạy bằng seed có thể tái hiện**, giữ input lỗi. Dùng framework có shrinking khi tập dữ liệu phức tạp.
7. **Đọc báo cáo phân phối**: mỗi subtype/guard có xuất hiện đủ không? Nếu có nhánh chưa được chạm, sửa generator hoặc thêm test tường minh.
8. **Lưu phản ví dụ thành test cố định** và sửa implementation. Sau khi sửa, chạy lại toàn bộ suite.
9. **Khi thêm subtype hoặc đổi domain**, cập nhật đồng thời đặc tả, generator, thuộc tính và regression tests.
10. **Duy trì chi phí hợp lý**: vài trăm/thousands tries nhanh trong CI; kiểm thử sinh dữ liệu rất lớn hoặc kiểm thử tích hợp đắt có thể tách sang lịch riêng.

### Checklist code review cho property test

- [ ] Property có phát biểu **hợp đồng domain**, không chỉ khẳng định implementation giống chính nó?
- [ ] Generator sinh được mọi subtype chính và null ở các tầng có thể null?
- [ ] Có boundary values cho guard `when` và thứ tự case?
- [ ] Phân biệt input hợp lệ và input bất hợp lệ?
- [ ] Có test độc lập cho `MatchException`/`NullPointerException` nếu domain có đường lỗi đó?
- [ ] Có seed, counterexample và chiến lược shrink/replay rõ ràng?
- [ ] Oracle có được viết độc lập, tránh copy-paste thuật toán?
- [ ] Metamorphic relation có precondition đúng, không tạo false positive?
- [ ] Có quan sát coverage/phân phối thay vì chỉ đếm số lượng `tries`?
- [ ] Test có độc lập với thời gian, thứ tự chạy, hệ thống bên ngoài và global mutable state?

## 9. Bài tập thực hành

**Bài 1 — Bắt lỗi biên.** Thay `grams > 5_000` bằng `grams >= 5_000` trong `classify`. Chạy chương trình: test boundary đầu tiên phải phát hiện `Physical(..., 5000)`. Khôi phục dấu `>` sau bài tập.

**Bài 2 — Null trong nested pattern.** Xóa nhánh `case Physical(var id, var city, var grams)` và thử các input `Physical(..., null, 10)`, `Physical(..., City(null), 10)`. Cân nhắc yêu cầu exhaustiveness của compiler và hành vi runtime. Không tự suy luận rằng `case null` xử lý được record con null.

**Bài 3 — Sinh thêm dữ liệu số.** Bổ sung `Integer.MAX_VALUE`/`MIN_VALUE` trong generator (đã có), rồi thêm một property không dùng phép toán gây overflow khi kiểm tra ngưỡng. Viết assertion có message chứa input gây lỗi.

**Bài 4 — Độ phủ thực tế.** Thống kê trong 20.000 lượt có bao nhiêu trường hợp `HEAVY`, `STANDARD`, `INVALID_PHYSICAL`, `DIGITAL`, `INVALID_DIGITAL`, `UNKNOWN` và `MISSING`. Nếu một nhóm có 0 mẫu, điều chỉnh generator hoặc thêm test cụ thể.

**Bài 5 — Chuyển sang jqwik.** Tạo `Arbitrary<Parcel>` kết hợp tất cả subtype và nullable components, viết `@Property` so với `reference`, rồi thử tạo bug ở ngưỡng để quan sát shrink/counterexample.

**Kết luận:** Property-based testing cho pattern matching bắt đầu bằng **hợp đồng và cấu trúc đầu vào**, không phải vòng lặp random. Một suite tốt mô hình hóa subtype, nested record, null, guard boundary và thứ tự case, đồng thời dùng **oracle độc lập**, **metamorphic relations** và **counterexample có thể tái hiện**. Với framework như jqwik, cơ chế shrinking giúp chuyển một trường hợp lỗi phức tạp thành ví dụ gọn để debug và bổ sung regression test.

### Tài liệu tham khảo

- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 394 — Pattern Matching for instanceof: https://openjdk.org/jeps/394
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- jqwik User Guide — Generators, Property, @ForAll, @Provide, Shrinking: https://jqwik.net/docs/current/user-guide
