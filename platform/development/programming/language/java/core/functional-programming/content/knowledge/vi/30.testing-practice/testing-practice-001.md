# Kiểm thử hàm thuần bằng bảng đầu vào và đầu ra trong Java

## 1. Mục tiêu: biến quy tắc nghiệp vụ thành những trường hợp kiểm thử rõ ràng

Một **hàm thuần** (*pure function*) có hai đặc điểm quan trọng:

1. **Cùng một đầu vào, cùng một kết quả quan sát được**: kết quả không phụ thuộc đồng hồ, số ngẫu nhiên, dữ liệu global có thể thay đổi hay lịch sử những lần gọi trước.
2. **Không gây tác dụng phụ quan sát được**: không chỉnh sửa tham số mutable, không cập nhật biến global, không ghi file, database hoặc gọi mạng như một phần của tính toán.

Ví dụ thuần:

```java
static int square(int n) {
    return n * n;
}
```

Ví dụ **không thuần**:

```java
static int counter = 0;

static int nextNumber() {
    return ++counter;
}
```

`nextNumber()` không có tham số nhưng mỗi lần gọi có thể cho kết quả khác nhau. Dù có thể viết test cho một chuỗi lời gọi, test đó phải phụ thuộc thứ tự và trạng thái ban đầu; không còn là kiểm thử đầu vào → đầu ra độc lập.

Khi hàm thuần, cách kiểm thử đặc biệt trực tiếp là lập **bảng các trường hợp đầu vào và đầu ra kỳ vọng**. Mỗi hàng trong bảng là một test case. Code kiểm thử có thể duyệt mọi hàng bằng cùng một quy trình:

```text
test case = (tên ca, input, expected output)

đối với từng case:
    actual = function(input)
    so sánh actual với expected
    nếu khác → báo lỗi kèm tên case, input, expected và actual
```

Cách này thường được gọi là **table-driven testing** hoặc **data-driven testing**. Nó phù hợp với Java Core, functional programming, các quy tắc chuyển đổi dữ liệu, hàm chuẩn hóa, tính phí, phân loại, validator và các phép toán có nhánh.

Sau bài này, bạn sẽ biết thiết kế bảng test có độ bao phủ ý nghĩa, chạy chúng bằng Java 17 không cần thư viện ngoài, kiểm tra các trường hợp ném ngoại lệ, tổ chức kiểm thử với JUnit 5 khi có dự án test và phân biệt *hàm thuần* với *hàm chỉ tình cờ cho kết quả giống nhau*.

## 2. Vì sao hàm thuần dễ kiểm thử?

Hàm thuần có thể được hiểu như ánh xạ:

```text
f: Input → Output
```

Với các giá trị đầu vào đã xác định:

```text
f(0)     → 0
f(2)     → 4
f(-3)    → 9
```

Khi không có dữ liệu ngoài tác động, mỗi test có thể được chạy độc lập:

- Không cần tạo database giả cho một phép tính thuần.
- Không cần đặt lại biến static trước mỗi test.
- Không cần kiểm tra xem test khác chạy trước có sửa state không.
- Không cần `Thread.sleep` để chờ thời gian hay dựa vào thứ tự ngẫu nhiên.
- Có thể chạy cùng input nhiều lần hoặc song song mà không bị side effect của **chính hàm** làm nhiễu kết quả.

Nhưng **hàm thuần không tự động đúng**. Nếu triển khai một công thức sai, nó vẫn có thể trả cùng kết quả sai mỗi lần. Vì vậy bảng test cần các đầu ra kỳ vọng được tính **độc lập từ đặc tả**, không chỉ sao chép cách tính của code đang kiểm thử.

Một test chạy qua 100 lần cũng không chứng minh toán học rằng hàm không có tác dụng phụ. Nó cung cấp bằng chứng cho những trường hợp cụ thể. Thiết kế hàm, xem xét các biến tham chiếu và đánh giá bất biến nghiệp vụ vẫn cần thiết.

## 3. Ví dụ: một hàm tính phí giao hàng có nhiều nhánh

Giả sử quy tắc của hệ thống là:

- Đầu vào `subtotal` là **tổng tiền hàng bằng đồng**, không âm.
- `express` là cờ yêu cầu giao nhanh.
- Khi `subtotal` **từ 100.000 đồng trở lên**:
  - Giao thường: miễn phí (`0`).
  - Giao nhanh: `15.000`.
- Khi `subtotal` **dưới 100.000 đồng**:
  - Giao thường: `10.000`.
  - Giao nhanh: `25.000`.
- `subtotal < 0` là đầu vào sai, phải ném `IllegalArgumentException`.

Hàm thuần tương ứng:

```java
static int shippingFee(int subtotal, boolean express) {
    if (subtotal < 0) {
        throw new IllegalArgumentException("subtotal must be nonnegative");
    }
    if (subtotal >= 100_000) {
        return express ? 15_000 : 0;
    }
    return express ? 25_000 : 10_000;
}
```

Hàm không đọc giá trị ngoài tham số, không sửa trạng thái và trả kết quả theo một bảng quy tắc xác định. Ném một ngoại lệ theo điều kiện đầu vào **không tự nó làm hàm trở thành không thuần**: ở đây loại ngoại lệ được xác định bởi input. Tuy nhiên, test có thể chỉ so loại ngoại lệ hoặc so cả thông điệp, tùy hợp đồng ứng dụng.

### Bảng ca kiểm thử đầu vào → đầu ra

| ID | `subtotal` | `express` | Kết quả mong đợi | Ý nghĩa |
| --- | ---: | :---: | ---: | --- |
| F01 | 0 | `false` | 10000 | Nhỏ nhất hợp lệ, giao thường |
| F02 | 0 | `true` | 25000 | Nhỏ nhất hợp lệ, giao nhanh |
| F03 | 99999 | `false` | 10000 | Ngay dưới ngưỡng, giao thường |
| F04 | 99999 | `true` | 25000 | Ngay dưới ngưỡng, giao nhanh |
| F05 | 100000 | `false` | 0 | Chính xác ngưỡng, giao thường |
| F06 | 100000 | `true` | 15000 | Chính xác ngưỡng, giao nhanh |
| F07 | 180000 | `false` | 0 | Trên ngưỡng, giao thường |
| F08 | 180000 | `true` | 15000 | Trên ngưỡng, giao nhanh |

Có thể coi đây là một **bảng chân trị mở rộng** theo hai nhánh `express` và ba vùng giá trị: dưới ngưỡng, tại ngưỡng, trên ngưỡng. Chọn `99.999` và `100.000` có chủ đích để phát hiện lỗi `>` thay vì `>=`.

Bảng này có thêm một ca ngoại lệ:

| ID | `subtotal` | `express` | Kỳ vọng |
| --- | ---: | :---: | --- |
| E01 | -1 | `false` | `IllegalArgumentException` |

Đây là một chính sách từ chối dữ liệu, không phải kết quả `0`. Nếu bạn chỉ ghi `expected = 0` cho số âm, test có thể che một bug quan trọng.

### Không viết test kỳ vọng từ chính hàm đang được test

Sai về mục đích kiểm thử:

```java
int expected = shippingFee(100_000, false);
int actual = shippingFee(100_000, false);
assertEquals(expected, actual);
```

Hai vế đều chạy cùng một triển khai, nên bug trong hàm có thể xuất hiện ở cả `expected` lẫn `actual`. Kỳ vọng phải đến từ đặc tả nghiệp vụ: với `100_000` và giao thường thì `0`.

## 4. Thiết kế bảng cho hàm chuẩn hóa chuỗi

Ngoài các phép tính số, bảng input-output rất hữu ích cho transformation.

Giả sử hàm `normalizeTag(String raw)` có quy tắc:

1. `null` bị từ chối bằng `NullPointerException`.
2. Cắt khoảng trắng ở hai đầu bằng `String.strip()`.
3. Nếu sau cắt là chuỗi rỗng, ném `IllegalArgumentException`.
4. Chuyển chuỗi sang chữ hoa bằng `toUpperCase(Locale.ROOT)`.
5. Không tự ý loại khoảng trắng **ở giữa** chuỗi.

```java
static String normalizeTag(String raw) {
    Objects.requireNonNull(raw, "raw");
    String cleaned = raw.strip();
    if (cleaned.isEmpty()) {
        throw new IllegalArgumentException("tag must not be blank");
    }
    return cleaned.toUpperCase(Locale.ROOT);
}
```

`Locale.ROOT` dùng quy tắc không phụ thuộc locale mặc định của máy cho một mã/tag kỹ thuật minh họa. Với ngôn ngữ tự nhiên hoặc quy tắc tên riêng, cần chọn locale phù hợp nghiệp vụ; không mặc định mọi văn bản đều nên uppercase theo `Locale.ROOT`.

### Bảng thành công

| ID | Input | Expected | Phần hành vi |
| --- | --- | --- | --- |
| T01 | `"java"` | `"JAVA"` | Chuyển sang chữ hoa |
| T02 | `"  stream  "` | `"STREAM"` | Cắt khoảng trắng hai đầu |
| T03 | `"a b"` | `"A B"` | Giữ khoảng trắng bên trong |
| T04 | `"trà"` | `"TRÀ"` | Chữ có dấu |
| T05 | `"API"` | `"API"` | Đã chuẩn hóa |
| T06 | `"\t tool \t"` | `"TOOL"` | Tab ngoài chuỗi |

### Bảng lỗi

| ID | Input | Kỳ vọng |
| --- | --- | --- |
| E02 | `" \t "` | `IllegalArgumentException` |
| E03 | `null` | `NullPointerException` |

Khi ghi test trong bảng, hãy biểu diễn dữ liệu có ký tự vô hình rõ ràng: `" \t "` là một dấu cách, một tab, rồi dấu cách. Nếu test chỉ hiển thị chuỗi như văn bản thường, rất dễ bỏ sót lỗi liên quan whitespace.

Chọn nhiều dạng input giúp phát hiện bug mà chỉ kiểm thử `"java"` không bắt được: bỏ sót trim, xóa cả khoảng trắng nội bộ, xử lý locale không ổn định hoặc không có chính sách với null/blank.

## 5. Cách triển khai table-driven tests bằng `record` và vòng lặp

Trong Java 17, `record` rất phù hợp để biểu diễn **mỗi hàng dữ liệu kiểm thử**:

```java
record FeeCase(String id, int subtotal, boolean express, int expected) {}
record TagCase(String id, String input, String expected) {}
```

Một `record` lưu dữ liệu cho một case mà không cần tự viết constructor, getters, `equals`, `hashCode`, `toString`. Dù record bản thân không cho gán lại các thành phần, nó chỉ **bất biến nông**: nếu thành phần chứa `List` mutable, nội dung List vẫn có thể thay đổi. Ví dụ `int`, `boolean`, `String` không có rủi ro thay đổi nội bộ như thế.

Bộ kiểm thử lặp qua từng case:

```java
for (FeeCase test : feeCases) {
    int actual = shippingFee(test.subtotal(), test.express());
    checkEquals(test.expected(), actual, test.id());
}
```

Ưu điểm so với chép đi chép lại hàng chục câu `if`:

- Mọi case đi qua cùng logic assert.
- Thêm ca mới chỉ cần thêm một hàng.
- ID giúp xác định ca sai.
- Kết quả kỳ vọng dễ rà soát bằng mắt như một bảng đặc tả.
- Có thể tái sử dụng bảng trong JUnit, file CSV hoặc một test runner khác khi cần.

Tuy nhiên, **bảng dữ liệu không thay thế yêu cầu thiết kế test**. Hai mươi hàng cùng giá trị thường không tốt bằng tám hàng đại diện các nhánh và biên được xác định có chủ đích.

## 6. Chương trình Java 17 hoàn chỉnh: bảng thành công, bảng lỗi và kiểm thử hàm thuần

Tạo file **`PureFunctionTableTests.java`**:

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.stream.Stream;

public class PureFunctionTableTests {
    // Các hàm nghiệp vụ cần kiểm thử.
    static int shippingFee(int subtotal, boolean express) {
        if (subtotal < 0) {
            throw new IllegalArgumentException(
                    "subtotal must be nonnegative");
        }
        if (subtotal >= 100_000) {
            return express ? 15_000 : 0;
        }
        return express ? 25_000 : 10_000;
    }

    static String normalizeTag(String raw) {
        Objects.requireNonNull(raw, "raw");
        String cleaned = raw.strip();
        if (cleaned.isEmpty()) {
            throw new IllegalArgumentException(
                    "tag must not be blank");
        }
        return cleaned.toUpperCase(Locale.ROOT);
    }

    // Mỗi record tương ứng một dòng trong bảng ca kiểm thử.
    record FeeCase(String id, int subtotal,
                   boolean express, int expected) {}

    record TagCase(String id, String input, String expected) {}

    record FailureCase(
            String id,
            Class<? extends RuntimeException> expectedType,
            Runnable action) {}

    static void checkEquals(Object expected, Object actual,
                            String caseId) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    caseId + ": expected=" + expected
                            + ", actual=" + actual);
        }
    }

    static void checkThrows(
            Class<? extends RuntimeException> expectedType,
            Runnable action, String caseId) {
        try {
            action.run();
        } catch (RuntimeException actual) {
            if (expectedType.isInstance(actual)) {
                return;
            }
            throw new AssertionError(
                    caseId + ": wrong exception type; expected="
                            + expectedType.getSimpleName()
                            + ", actual="
                            + actual.getClass().getSimpleName(),
                    actual);
        }
        throw new AssertionError(
                caseId + ": expected "
                        + expectedType.getSimpleName()
                        + " but no exception was thrown");
    }

    static int testFees() {
        List<FeeCase> cases = List.of(
                new FeeCase("F01", 0, false, 10_000),
                new FeeCase("F02", 0, true, 25_000),
                new FeeCase("F03", 99_999, false, 10_000),
                new FeeCase("F04", 99_999, true, 25_000),
                new FeeCase("F05", 100_000, false, 0),
                new FeeCase("F06", 100_000, true, 15_000),
                new FeeCase("F07", 180_000, false, 0),
                new FeeCase("F08", 180_000, true, 15_000));

        for (FeeCase test : cases) {
            int actual = shippingFee(
                    test.subtotal(), test.express());
            checkEquals(test.expected(), actual, test.id());

            // So lại cùng input, xác nhận trong ca này
            // không phát hiện phụ thuộc lịch sử gọi hàm.
            int repeated = shippingFee(
                    test.subtotal(), test.express());
            checkEquals(actual, repeated,
                    test.id() + " repeated");
        }
        return cases.size();
    }

    static int testTags() {
        List<TagCase> cases = List.of(
                new TagCase("T01", "java", "JAVA"),
                new TagCase("T02", "  stream  ", "STREAM"),
                new TagCase("T03", "a b", "A B"),
                new TagCase("T04", "trà", "TRÀ"),
                new TagCase("T05", "API", "API"),
                new TagCase("T06", "\t tool \t", "TOOL"));

        for (TagCase test : cases) {
            String actual = normalizeTag(test.input());
            checkEquals(test.expected(), actual, test.id());
            checkEquals(actual, normalizeTag(test.input()),
                    test.id() + " repeated");

            // Với các giá trị mẫu hợp lệ, chuẩn hóa lần nữa
            // không làm đổi kết quả đã chuẩn hóa.
            checkEquals(actual, normalizeTag(actual),
                    test.id() + " normalized twice");
        }
        return cases.size();
    }

    static int testFailures() {
        List<FailureCase> cases = List.of(
                new FailureCase(
                        "E01",
                        IllegalArgumentException.class,
                        () -> shippingFee(-1, false)),
                new FailureCase(
                        "E02",
                        IllegalArgumentException.class,
                        () -> normalizeTag(" \t ")),
                new FailureCase(
                        "E03",
                        NullPointerException.class,
                        () -> normalizeTag(null)));

        for (FailureCase test : cases) {
            checkThrows(test.expectedType(),
                    test.action(), test.id());
        }
        return cases.size();
    }

    public static void main(String[] args) {
        int feeCases = testFees();
        int tagCases = testTags();
        int errorCases = testFailures();

        // Dùng hàm thuần trong pipeline: từng kết quả
        // chỉ phụ thuộc giá trị tag đầu vào.
        List<String> composition = Stream.of(
                        " java ", "Stream", " api ")
                .map(PureFunctionTableTests::normalizeTag)
                .toList();
        checkEquals(List.of("JAVA", "STREAM", "API"),
                composition, "composition");

        System.out.println("feeCases=" + feeCases);
        System.out.println("tagCases=" + tagCases);
        System.out.println("errorCases=" + errorCases);
        System.out.println("composition=" + composition);
        System.out.println("tests=PASS");
    }
}
```

Chạy bằng **JDK 17 hoặc mới hơn**:

```bash
javac -encoding UTF-8 PureFunctionTableTests.java
java PureFunctionTableTests
```

Stdout khi tất cả ca thành công:

```text
feeCases=8
tagCases=6
errorCases=3
composition=[JAVA, STREAM, API]
tests=PASS
```

Các kiểm tra không phụ thuộc cờ JVM `-ea`, vì `checkEquals` và `checkThrows` trực tiếp ném `AssertionError` khi có sai lệch. Khi một case thất bại, thông báo chứa ID (ví dụ `F05`, `T04`, `E02`) và kỳ vọng tương ứng, giúp xác định chính xác hàng nào trong bảng cần điều tra.

### Vì sao chia thành ba bảng?

- `FeeCase`: hai input kiểu `int`, `boolean`, một output kiểu `int`.
- `TagCase`: một input `String`, một output `String`.
- `FailureCase`: thay vì giá trị trả về, kỳ vọng là **loại ngoại lệ**.

Không cần ép ngoại lệ thành giá trị giả như `-1` hoặc `null` nếu API thiết kế để ném lỗi. Bộ kiểm thử xác nhận hợp đồng hiện có; khi bạn thay đổi hợp đồng theo yêu cầu sản phẩm, hãy cập nhật bảng và mã cùng nhau.

### Vai trò của `checkThrows`

Một test ngoại lệ chỉ pass nếu có **đúng loại ngoại lệ**. Nếu hàm không ném gì, test fail. Nếu ném một loại `RuntimeException` khác, test cũng fail kèm lỗi gốc.

Không nên viết:

```java
try {
    shippingFee(-1, false);
} catch (Exception ignored) {
    // Sai: test coi mọi exception đều là thành công.
}
```

Đoạn trên còn có vấn đề: nếu hàm **không ném lỗi**, test cũng không thất bại. Bộ kiểm thử đúng phải kiểm tra cả việc ném ngoại lệ và loại ngoại lệ.

### Kiểm tra lặp lại không đồng nghĩa chứng minh tính thuần

Trong `testFees()` và `testTags()`, cùng input được gọi hai lần và so sánh kết quả. Việc này có thể phát hiện một số lỗi có state bị thay đổi. Nhưng một hàm đọc đồng hồ mà tình cờ trả cùng giá trị ở hai lần gần nhau vẫn có thể qua test; một hàm ghi log vẫn có side effect dù output không đổi.

**Tính thuần là đặc điểm thiết kế cần đánh giá bằng code và hợp đồng**, không thể được chứng minh chỉ bằng kiểm thử lặp lại trên số ít input.

## 7. Các bước xây bảng đầu vào–đầu ra hiệu quả

### Bước 1: Viết đặc tả bằng ngôn ngữ nghiệp vụ

Không bắt đầu từ implementation. Ví dụ:

> Với đơn hàng từ 100.000 đồng, giao thường miễn phí; giao nhanh 15.000 đồng. Dưới ngưỡng, giao thường 10.000 và giao nhanh 25.000. Tổng âm không được chấp nhận.

Đặc tả là nguồn tính expected, tránh test chỉ sao chép sai lầm của hàm.

### Bước 2: Liệt kê lớp tương đương

Các input cho `shippingFee` có thể chia thành:

| Trường | Lớp dữ liệu |
| --- | --- |
| `subtotal` | Âm |
| `subtotal` | Không âm và dưới 100.000 |
| `subtotal` | Bằng hoặc trên 100.000 |
| `express` | `false` |
| `express` | `true` |

Kết hợp các nhánh quan trọng để đạt bao phủ. Không cần tạo quá nhiều dữ liệu ngẫu nhiên khi mọi giá trị trong cùng lớp dự kiến có cùng hành vi; nhưng phải đặc biệt chú ý **ranh giới**.

### Bước 3: Chọn giá trị biên

Với ngưỡng `100_000`, các giá trị điển hình là:

```text
99_999     : ngay dưới
100_000    : chính xác ngưỡng
100_001    : ngay trên
```

Đây là kỹ thuật *boundary value analysis*. Bảng chính dùng `99_999`, `100_000`, `180_000`; có thể thêm `100_001` khi cần xác minh rõ biên ngay trên. Dữ liệu ở rất xa ngưỡng có thể kiểm tra hành vi bình thường, nhưng ít có sức phát hiện lỗi `>`/`>=` hơn những giá trị sát ngưỡng.

### Bước 4: Chọn cả ca không hợp lệ

Dữ liệu lỗi là một phần của hợp đồng. Nếu `subtotal < 0` thì ghi kỳ vọng `IllegalArgumentException`, không để tester đoán một giá trị mặc định. Với chuỗi, cần các ca `null`, rỗng, chỉ có whitespace hoặc ký tự đặc biệt tùy yêu cầu.

### Bước 5: Đặt tên case có ý nghĩa

`F05` là ID gọn, nhưng với tập test lớn nên có thêm tên như `atThresholdRegular` hoặc `blankTagRejected`. Tên giúp phân biệt điều kiện đầu vào và mục tiêu của case.

Nếu một test có mười input khác nhau nhưng tất cả tên là `"test1"`, `"test2"` thì khi thất bại, người duy trì phải đoán ý định. Trong chương trình đầy đủ, ID tương ứng với bảng giải thích cụ thể trong README.

### Bước 6: Lựa chọn phép so sánh theo kiểu dữ liệu

- Primitive số nguyên, `String`, `record` chỉ chứa giá trị có thể so bằng `Objects.equals`.
- Mảng cần `Arrays.equals` hoặc `Arrays.deepEquals` tùy số chiều, **không** chỉ dựa vào `Objects.equals` để so phần tử.
- Số thực có sai số làm tròn cần độ lệch cho phép (*tolerance*) hoặc quy tắc làm tròn chính thức.
- Danh sách có thứ tự cần so cả **nội dung và thứ tự**; Map thường so bằng `equals` mà không phụ thuộc thứ tự in.
- Khi kết quả chứa `Optional`, phải phân biệt `Optional.empty()` và khóa Map không tồn tại.
- Với ngoại lệ, kiểm tra loại và khi cần, thông điệp hoặc mã lỗi theo hợp đồng.

### Bước 7: Chạy toàn bảng, không dừng ở một ví dụ đẹp

Một case thành công không chứng minh các nhánh còn lại. Bảng kiểm thử nên được chạy tự động qua mỗi lần thay đổi logic, đặc biệt khi điều chỉnh ngưỡng hoặc các quy tắc chuẩn hóa.

## 8. Bảng test giúp phát hiện những lỗi cụ thể như thế nào?

### Lỗi so sánh sai ở ngưỡng

Giả sử ai đó vô tình sửa:

```java
if (subtotal > 100_000) {
    return express ? 15_000 : 0;
}
```

thay cho `>=`. Các ca `F05`, `F06` với `subtotal=100_000` sẽ thất bại. Nếu bảng chỉ có `0` và `180_000`, bug này có thể không bị bắt.

### Lỗi đảo điều kiện boolean

Nếu coder viết nhầm:

```java
return express ? 10_000 : 25_000;
```

ở nhánh dưới ngưỡng, các ca `F01`, `F02`, `F03`, `F04` sẽ phát hiện. Bảng có đủ hai giá trị boolean là một quyết định thiết kế test, không phải ngẫu nhiên.

### Lỗi bỏ qua `strip()`

Nếu `normalizeTag("  stream  ")` chỉ gọi `toUpperCase`, kết quả sẽ là `"  STREAM  "` thay vì `"STREAM"`, test `T02` thất bại.

### Lỗi xóa khoảng trắng ở giữa

Nếu một refactor tự thay tất cả khoảng trắng bằng chuỗi rỗng, `normalizeTag("a b")` trả `"AB"` thay vì `"A B"`, test `T03` thất bại. Điều này cho thấy bảng cần các ca **giữ nguyên theo quy tắc**, không chỉ các ca cần thay đổi.

### Lỗi xử lý `null`

Nếu bỏ `Objects.requireNonNull(raw)` và vô tình trả `"null"` hoặc `""`, `E03` thất bại. Nếu thay NPE bằng IAE, test cũng báo khác hợp đồng hiện tại. Có những API chọn IAE cho null; điều quan trọng là chính sách phải được ghi rõ và test tương ứng.

## 9. Nâng cấp sang JUnit 5 `@ParameterizedTest`

Trong dự án Java thật, JUnit Jupiter cho phép chạy cùng một phương thức test với nhiều hàng dữ liệu. Đây là cách phổ biến để tránh viết vòng lặp và test runner thủ công.

Ví dụ dưới đây là **trích đoạn đặt trong một lớp test của dự án đã cấu hình JUnit Jupiter và `junit-jupiter-params`**; nó không phải file Java độc lập chỉ chạy bằng lệnh `java` không có dependency. Các hàm nghiệp vụ thuộc lớp `PureFunctionTableTests` ở phần 6.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.NullSource;
import org.junit.jupiter.params.provider.ValueSource;

class PureFunctionParameterizedTest {
    @ParameterizedTest(name = "subtotal={0}, express={1}, fee={2}")
    @CsvSource({
        "0, false, 10000",
        "0, true, 25000",
        "99999, false, 10000",
        "99999, true, 25000",
        "100000, false, 0",
        "100000, true, 15000",
        "180000, false, 0",
        "180000, true, 15000"
    })
    void feeMatchesTable(
            int subtotal, boolean express, int expected) {
        assertEquals(
                expected,
                PureFunctionTableTests.shippingFee(subtotal, express));
    }

    @ParameterizedTest
    @ValueSource(strings = {" ", " \t ", "\t"})
    void blankTagIsRejected(String raw) {
        assertThrows(IllegalArgumentException.class,
                () -> PureFunctionTableTests.normalizeTag(raw));
    }

    @ParameterizedTest
    @NullSource
    void nullTagIsRejected(String raw) {
        assertThrows(NullPointerException.class,
                () -> PureFunctionTableTests.normalizeTag(raw));
    }
}
```

Các converter của JUnit xử lý chuỗi CSV thành kiểu `int` và `boolean`. Với dữ liệu chứa dấu phẩy, quote, `null`, chuỗi rỗng hoặc record nhiều trường, `@MethodSource` thường biểu diễn rõ ràng hơn `@CsvSource`, vì nó tạo trực tiếp các đối tượng lập luận.

Ví dụ phương thức nguồn (trích đoạn, cần thêm import `Stream`, `Arguments`):

```java
static Stream<Arguments> tagCases() {
    return Stream.of(
            Arguments.of("java", "JAVA"),
            Arguments.of("  stream  ", "STREAM"),
            Arguments.of("a b", "A B"),
            Arguments.of("trà", "TRÀ"));
}

@ParameterizedTest
@MethodSource("tagCases")
void normalizesTags(String raw, String expected) {
    assertEquals(expected, PureFunctionTableTests.normalizeTag(raw));
}
```

Ở đây cần `org.junit.jupiter.params.provider.MethodSource` và `org.junit.jupiter.params.provider.Arguments` cùng các import JUnit cho phương thức test. Đây là minh họa về **cấu trúc** trong class test; nó không phải ví dụ độc lập để copy vào shell. Với JUnit, mỗi hàng được báo thành một test invocation nên kết quả CI thường dễ theo dõi hơn một vòng `for` tự viết.

**Không cần JUnit để hiểu kỹ thuật table-driven testing**: bản Java 17 đầy đủ ở phần 6 đã chạy độc lập. JUnit hữu ích khi tích hợp hệ thống build, lifecycle, báo cáo và công cụ IDE/CI.

## 10. Kiểm thử hàm nhiều tham số và kết quả phức tạp

Một hàm thuần không bắt buộc chỉ nhận một primitive và trả một primitive. Ví dụ:

```java
record Order(int quantity, int unitPrice) {}
record Receipt(int subtotal, int shippingFee, int total) {}
```

Một hàm `price(Order order, boolean express)` có thể nhận record đầu vào và trả `Receipt`; bảng test có thể dùng:

```java
record PriceCase(
        String id,
        Order order,
        boolean express,
        Receipt expected) {}
```

Khi record chỉ chứa primitive và `String`, `equals` do record tạo ra thường hỗ trợ so sánh cấu trúc rất tiện. Nếu record chứa một `List` hoặc object mutable, hãy xác định bất biến dữ liệu, chính sách copy và sự phù hợp của `equals`.

Nếu kết quả là `List`, chỉ dùng `List.equals` khi yêu cầu nghiệp vụ **phụ thuộc thứ tự**. Nếu kết quả là một nhóm khóa, `Map.equals` so mapping không dựa vào thứ tự duyệt, còn việc xuất báo cáo theo thứ tự phải được kiểm thử riêng bằng danh sách khóa hoặc cấu trúc `TreeMap`/`LinkedHashMap` theo hợp đồng.

Bảng test cũng có thể gồm:

| ID | Input | Expected output |
| --- | --- | --- |
| P01 | Order(2, 40000), false | Receipt(80000, 10000, 90000) |
| P02 | Order(1, 100000), false | Receipt(100000, 0, 100000) |
| P03 | Order(1, 100000), true | Receipt(100000, 15000, 115000) |

Đây là **bảng đặc tả mở rộng**, không phải ca đang chạy trong `PureFunctionTableTests.java`; bạn cần tự triển khai hàm `price` và test tương ứng theo công thức đã nêu.

## 11. Kiểm thử ngoại lệ, lỗi miền nghiệp vụ và `null`

Một bảng test tốt phải nêu rõ **mỗi hàng kết thúc như thế nào**. Không nên trộn ba trạng thái mà không có quy ước:

- **Có kết quả hợp lệ**: so với `expected`.
- **Đầu vào bị từ chối bằng exception**: kiểm tra loại exception, có thể cả thông điệp khi hợp đồng đòi.
- **Đầu vào hợp lệ nhưng không có kết quả**: có thể trả `Optional.empty()` hoặc một kiểu kết quả `Result` riêng, không nhất thiết ném ngoại lệ.

Ví dụ hàm thuần `parsePositiveInt(String)` có thể trả `OptionalInt.empty()` khi chuỗi không parse được. Khi đó bảng phải ghi đúng kiểu kỳ vọng, không thay bằng `0` vì số 0 và “không có số” có thể mang hai ý nghĩa khác nhau.

Không dùng test dạng:

```java
try {
    functionWithInvalidInput();
} catch (RuntimeException e) {
    // Mọi lỗi đều được chấp nhận.
}
```

Nó không xác nhận loại lỗi và không thất bại khi hàm không ném gì. Tốt hơn là `assertThrows` trong JUnit hoặc `checkThrows` trong Java Core, như ở phần 6.

Một điểm tinh tế: nếu test yêu cầu đúng **thông điệp** ngoại lệ, thay đổi cách diễn đạt thông điệp cũng làm test fail. Chỉ cố định message khi nó là một phần API contract; còn nếu chỉ cần loại lỗi, so loại để giảm test giòn (*brittle*).

## 12. Tính lặp lại, thứ tự ca kiểm thử và trạng thái dùng chung

Với hàm thuần, bạn muốn mỗi ca tự đứng độc lập. Nếu test A cần chạy trước test B để đặt một biến static, bạn đang kiểm thử một workflow trạng thái, **không còn là một bảng ánh xạ đầu vào–đầu ra độc lập thuần**.

Phản ví dụ:

```java
static int lastSubtotal = 0;

static int shippingFeeWithState(boolean express) {
    return lastSubtotal >= 100_000
            ? (express ? 15_000 : 0)
            : (express ? 25_000 : 10_000);
}
```

`shippingFeeWithState(false)` phụ thuộc vào `lastSubtotal` từ lần chạy trước. Bảng chỉ gồm cột `express` và `expected` là **thiếu dữ liệu** để xác định kết quả. Phải refactor để `subtotal` là tham số hoặc dùng một loại test mô tả cả trạng thái trước và sau.

Với hàm thuần, có thể chạy các ca theo thứ tự khác mà vẫn có cùng kết quả riêng từng case. Đây là lợi thế lớn khi chạy test trên CI hay phân phối test song song. Tuy nhiên **test runner** vẫn có thể phụ thuộc thứ tự nếu nó tự ghi trạng thái chia sẻ hoặc nếu từng case dùng dữ liệu đầu vào mutable. Hãy giữ bảng test bất biến hoặc tạo dữ liệu mới phù hợp cho mỗi ca.

### Đừng dùng giờ hệ thống hoặc random trực tiếp trong hàm đang kiểm thử

Ví dụ hàm:

```java
static boolean isExpired() {
    return java.time.Instant.now().isAfter(deadline);
}
```

Đoạn này là **phác thảo**, `deadline` phải được khai báo ở ngữ cảnh chứa nó. Hàm phụ thuộc đồng hồ và trạng thái bên ngoài nên không phải hàm thuần trên tập tham số hiện có. Cách tách dễ kiểm thử hơn:

```java
static boolean isExpired(
        java.time.Instant now, java.time.Instant deadline) {
    return now.isAfter(deadline);
}
```

Bảng giờ đầu vào có thể kiểm tra ca trước, tại và sau deadline bằng các `Instant` cố định. Code ở lớp ngoài mới chịu trách nhiệm gọi `Instant.now()` rồi truyền vào hàm. Cách này không chỉ giúp test ổn định mà còn giúp nhìn rõ mọi dependency.

Tương tự, thay vì gọi `Random` ẩn bên trong hàm tính toán, hãy truyền tham số hoặc truyền nguồn random vào tầng thực thi phù hợp; cần phân biệt rõ phần **tính toán thuần** với phần **lấy dữ liệu không thuần**.

## 13. Kết hợp bảng test với tính chất (*property*) của hàm

Bảng ví dụ kiểm tra những điểm cụ thể. Có thể bổ sung những **bất biến tổng quát** giúp bắt lỗi ngoài những điểm đó.

Với `shippingFee` theo đúng đặc tả:

1. Đầu vào hợp lệ có phí nằm trong tập `{0, 10000, 15000, 25000}`.
2. Với cùng `express`, tăng `subtotal` từ dưới lên trên ngưỡng không làm **tăng** phí.
3. Với cùng `subtotal`, phí giao nhanh không nhỏ hơn phí giao thường trong chính sách hiện tại.
4. `subtotal` âm luôn bị từ chối.
5. Nếu `subtotal >= 100000`, phí giao thường bằng `0`, giao nhanh bằng `15000`.

Đây là ví dụ của **property-based testing**: thay vì chỉ kiểm tra một số cặp input-output, ta xác nhận các quan hệ hoặc bất biến cho nhiều dữ liệu. Có thể triển khai bằng vòng lặp với các giá trị lựa chọn có hệ thống hoặc dùng thư viện property-based testing khi dự án có sẵn.

Ví dụ kiểm tra một bất biến trong Java Core (trích đoạn nằm trong cùng lớp với `shippingFee`):

```java
for (int subtotal : new int[]{0, 50_000, 99_999,
                               100_000, 100_001, 180_000}) {
    int regular = shippingFee(subtotal, false);
    int express = shippingFee(subtotal, true);

    if (express < regular) {
        throw new AssertionError(
                "express fee unexpectedly lower: " + subtotal);
    }
}
```

Không nên thay toàn bộ **expected cụ thể** bằng những bất biến quá yếu. Ví dụ hàm luôn trả `0` có thể thỏa “phí giao nhanh không nhỏ hơn phí thường” nhưng vẫn sai phần lớn bảng. Bảng test và property tests bổ sung lẫn nhau.

### Quan hệ biến hình (*metamorphic relation*)

Với các tag hợp lệ ở ví dụ, có thể kiểm tra:

```text
normalizeTag(normalizeTag(x)) == normalizeTag(x)
```

Đây là tính *idempotent* mong đợi cho những input mẫu và quy tắc chuẩn hóa được nêu. `testTags()` đã kiểm tra điều này sau mỗi trường hợp hợp lệ.

Nếu thêm các bước chuẩn hóa Unicode phức tạp hoặc quy tắc miền nghiệp vụ khác, hãy đánh giá lại điều kiện và miền áp dụng trước khi tuyên bố một property đúng với mọi chuỗi Unicode.

## 14. Tối ưu phạm vi test mà không tạo hàng trăm ca lặp lại

Bảng quá dài nhưng không đa dạng có thể khiến việc bảo trì khó. Một cách hợp lý là phân loại test:

| Nhóm | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Happy path | Hoạt động bình thường | `subtotal=50000`, `express=false` |
| Boundary | Sai khác `>` / `>=` | `99999`, `100000`, `100001` |
| Equivalence classes | Các nhánh nghiệp vụ | Giao thường vs giao nhanh |
| Invalid input | Chính sách từ chối | `subtotal=-1`, tag blank |
| Special characters | Whitespace/Unicode/locale | `" \t "`, `"trà"` |
| Stable/repeatable | Không phát hiện lệ thuộc state | Cùng input gọi hai lần |
| Composition | Dùng hàm trong pipeline | `Stream.map(PureFunctionTableTests::normalizeTag)` |
| Invariant | Quy tắc tổng quát | Phí express không thấp hơn regular |

Chọn data point **vì nó có ý nghĩa**, không phải vì muốn đạt số lượng test tối thiểu nào đó.

Nếu bảng lớn, có thể tách dữ liệu ra CSV/JSON, nhưng phải chú ý parse kiểu, ký tự Unicode, dấu phân cách, thông điệp lỗi và thứ tự dữ liệu. Với bảng nhỏ như bài này, viết `List.of(new FeeCase(...))` ngay trong test dễ rà soát và tránh dependency I/O. Test một hàm thuần không bắt buộc phải phụ thuộc file ngoài.

## 15. Các lỗi thường gặp khi test theo bảng

**Lỗi 1 — lấy kỳ vọng từ chính implementation.** Nếu expected được tính bằng cùng công thức sai, test mất giá trị. Hãy dựa trên quy tắc nghiệp vụ hoặc một oracle độc lập.

**Lỗi 2 — chỉ kiểm tra happy path.** Không có giá trị âm, null, blank hay sát ngưỡng thì bug ở ranh giới thường bị bỏ qua.

**Lỗi 3 — đổi nhầm `>` và `>=`.** Không kiểm thử đúng tại ngưỡng `100000` khiến lỗi khó phát hiện.

**Lỗi 4 — so kết quả bằng `==` khi là object.** Với `String`, `List`, `record`, cần hiểu `equals` và cấu trúc dữ liệu. Với mảng, dùng `Arrays.equals` thay vì so reference.

**Lỗi 5 — bắt mọi exception rồi coi là pass.** Test phải fail nếu không có exception hoặc exception sai loại.

**Lỗi 6 — dùng `assert` mặc định nhưng không bật `-ea`.** `assert` của ngôn ngữ Java có thể bị tắt; dùng assertion framework hoặc phương thức kiểm tra chủ động như ví dụ.

**Lỗi 7 — test phụ thuộc thứ tự chạy.** Các ca phải mang đủ đầu vào riêng, không dựa vào biến static do ca trước thiết lập.

**Lỗi 8 — so kết quả `double` như số nguyên tuyệt đối.** Phép toán dấu phẩy động có làm tròn; cần tolerance hoặc quy tắc chính xác phù hợp.

**Lỗi 9 — thiếu ID/caption cho case.** Khi chạy 200 hàng, cần xác định ngay case nào thất bại để debug.

**Lỗi 10 — nhầm “lặp lại kết quả” với “hàm thuần”.** Hàm có side effect nhưng trả một hằng số vẫn không thuần; cần xem xét hành vi ngoài output.

**Lỗi 11 — nhầm `null` với chuỗi `"null"`.** Chúng khác nhau; test cần biểu diễn rõ cả hai theo hợp đồng.

**Lỗi 12 — gom nhiều quy tắc trong một case mà không biết đang kiểm tra nhánh nào.** Mỗi hàng nên có mục tiêu rõ. Có thể thêm nhiều điều kiện, nhưng tên case và expected phải nêu phần hành vi quan trọng.

**Lỗi 13 — kỳ vọng thứ tự Map không được bảo đảm.** Nếu kết quả chỉ là map nhóm, `Map.equals` thường phù hợp. Nếu thứ tự khóa là yêu cầu, tạo và kiểm tra thứ tự rõ ràng.

**Lỗi 14 — để test sinh input dựa trên trạng thái ngẫu nhiên mà không có seed/log.** Khi thất bại, cần tái hiện được input. Table-driven tests dùng dữ liệu cố định là một đường nền ổn định; test random/property cần cơ chế tái hiện.

**Lỗi 15 — quên kiểm tra tác dụng phụ trên đối tượng đầu vào mutable.** Một hàm trả đúng List nhưng lén sửa List nguồn không còn thuần. Trong test, tạo snapshot để so trước/sau nếu input có thể đổi.

## 16. Khi nào hàm không thuần vẫn kiểm thử bằng bảng được?

Một hàm **không thuần** vẫn có thể được kiểm thử theo bảng, nhưng bảng phải mô tả đủ trạng thái hoặc môi trường:

```text
(input, initial state) → (return value, final state, observable effects)
```

Ví dụ một bộ đếm có trạng thái cần test sự chuyển trạng thái; một dịch vụ DB cần test dữ liệu trong kho và kết quả ghi; một API phụ thuộc thời gian cần đồng hồ giả. Đây là chủ đề kiểm thử stateful/integration rộng hơn.

Đối với bài này, ưu tiên **tách lõi thuần khỏi vỏ không thuần**:

```text
Đọc input từ mạng/file          ← I/O, không thuần
         │
         ▼
Parse/validate thành dữ liệu ổn định
         │
         ▼
Hàm thuần tính toán kết quả      ← bảng input/output
         │
         ▼
Ghi kết quả ra DB/UI            ← I/O, test tương tác riêng
```

Tách lớp như vậy giúp các bảng test của thuật toán nhanh, lặp lại được, không đòi setup hệ thống và vẫn để phần I/O được kiểm thử bằng cách phù hợp.

## 17. Bài tập thực hành

1. Bổ sung `FeeCase("F09", 100_001, false, 0)` và `FeeCase("F10", 100_001, true, 15_000)`. Giải thích việc kiểm thử ngay trên ngưỡng có tác dụng gì.
2. Sửa tạm điều kiện `subtotal >= 100_000` thành `subtotal > 100_000`. Xác định chính xác các case thất bại, rồi phục hồi code đúng.
3. Sửa tạm quy tắc `normalizeTag` bỏ `strip()`. Ca nào phát hiện bug? Còn ca nào vẫn pass?
4. Thiết kế bảng `record TaxCase(int amount, int ratePercent, int expected)` cho hàm tính thuế số nguyên. Xác định quy tắc làm tròn, overflow và trường hợp rate ngoài miền hợp lệ trước khi viết code.
5. Viết `record ClassifyCase(int score, String expected)` cho hàm phân loại điểm. Tạo test ở các ngưỡng 0, 50, 70, 90, 100 và ngay hai phía mỗi ranh giới theo quy tắc bạn tự công bố.
6. Thêm ca input `"a b"` và `"  a b  "` cho `normalizeTag`. Chứng minh khoảng trắng trong chuỗi không bị xóa ngoài ý muốn.
7. Viết `@ParameterizedTest` dùng `@MethodSource` cho `normalizeTag`; lưu ý cách truyền `null` hoặc chuỗi chứa dấu phẩy, tab.
8. Dùng bảng ca kiểm thử để phát hiện hàm `countDigits(int)` trả sai với `0`, số âm và giới hạn số nguyên. Quyết định chính sách số âm trước khi ghi expected.
9. Tách `Instant.now()` khỏi một hàm kiểm tra deadline: truyền `now` làm tham số. Viết bảng gồm trước, đúng tại và sau deadline.
10. Từ bảng test giao hàng, bổ sung kiểm tra bất biến “phí giao nhanh không nhỏ hơn phí giao thường” cho một tập subtotal hợp lệ và so sánh với việc chỉ kiểm tra output cụ thể.
11. Tạo một hàm cố tình cập nhật biến static trong lúc vẫn trả kết quả đúng. Giải thích vì sao table-driven output tests không tự phát hiện mọi side effect.
12. Tạo `List<Case>` không thể chỉnh sửa chứa các trường hợp test, chạy lại chúng theo thứ tự đảo và chứng minh kết quả mỗi ca vẫn giữ nguyên nếu hàm thuần và môi trường không đổi.

## 18. Tổng kết

**Kiểm thử hàm thuần bằng bảng đầu vào và đầu ra** là phương pháp biến đặc tả thành tập test case có cấu trúc:

- Mỗi hàng ghi rõ **input → expected output**, hoặc **input → expected exception**.
- Chọn dữ liệu theo **lớp tương đương, giá trị biên, ca không hợp lệ và tình huống có ký tự đặc biệt**.
- Dùng `record` và `List.of` để lưu các ca trong Java 17; chạy cùng một logic kiểm tra cho mọi hàng.
- Gắn ID hoặc tên ca để báo lỗi rõ ràng, không chỉ in `true/false`.
- Có thể chuyển cấu trúc sang JUnit 5 `@ParameterizedTest`/`@CsvSource`/`@MethodSource` khi dự án đã có JUnit.
- Bổ sung kiểm tra bất biến/property và thử cùng input nhiều lần, nhưng không coi đó là **chứng minh đầy đủ** tính thuần.
- Đưa các phụ thuộc như thời gian, random, I/O và trạng thái mutable ra khỏi lõi tính toán để các bảng test thực sự độc lập và ổn định.

Kết quả tốt không nằm ở số lượng hàng trong bảng, mà ở việc **mỗi hàng đại diện cho một quy tắc có thể sai**, kỳ vọng được xác định độc lập từ đặc tả và lỗi có thể tái hiện chính xác.
