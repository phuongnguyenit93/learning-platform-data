# Pipeline với nguồn rỗng, null, trùng lặp và dữ liệu biên

## 1. Vì sao phải thiết kế pipeline cho dữ liệu bất thường?

Một pipeline xử lý dữ liệu thường nhận đầu vào từ API, file, database, message broker hoặc một bước xử lý trước đó. Dữ liệu thực tế có thể chứa:

- Nguồn không có bản ghi nào.
- Tham chiếu nguồn bị null hoặc không được khởi tạo.
- Một phần tử null nằm giữa danh sách.
- Bản ghi tồn tại nhưng một hoặc nhiều field bị null.
- Chuỗi rỗng, chuỗi chỉ có khoảng trắng hoặc ID sai định dạng.
- Hai bản ghi có cùng khóa nghiệp vụ.
- Số ở sát giới hạn kiểu dữ liệu, phép cộng bị overflow.
- Timestamp ở ranh giới ngày, tháng, năm hoặc daylight-saving transition.
- Dữ liệu Unicode, precision/scale khác nhau hoặc giá trị vượt miền cho phép.

Nếu pipeline chỉ được kiểm thử với danh sách nhỏ, đầy đủ và sạch, các lỗi này thường xuất hiện muộn ở production. Một pipeline đáng tin cậy phải **xác định rõ hợp đồng dữ liệu**, phân biệt các trường hợp bất thường, có chính sách xử lý nhất quán và có test chứng minh hành vi tại biên.

Bài thuộc chủ đề cha **“Kiểm thử và tối ưu”**, đề bài trực tiếp **“Pipeline với nguồn rỗng, null, trùng lặp và dữ liệu biên”**. Nội dung sử dụng Java 17+ và các API Java hiện hành; ví dụ chạy độc lập không cần database hay thư viện ngoài. Trọng tâm là cách kiểm thử và tối ưu pipeline theo đúng semantics của dữ liệu, không che lỗi bằng các giá trị mặc định.

### Mục tiêu học tập

1. Phân biệt null source, empty source, null row và null field.
2. Đặt hợp đồng rõ ràng cho dữ liệu hợp lệ, dữ liệu bị từ chối và lỗi cấp nguồn.
3. Chọn duplicate key và quy tắc xử lý duplicate có tính xác định.
4. Xử lý ranh giới số nguyên, overflow, decimal precision và dữ liệu thời gian.
5. Giữ thứ tự và tính ổn định của kết quả.
6. Viết pipeline một lượt với độ phức tạp phù hợp.
7. Kiểm thử bằng boundary cases, invariants và các biến thể đầu vào.
8. Tách lỗi của một record khỏi lỗi khiến toàn bộ batch không thể xử lý.
9. Biết giới hạn của parallel processing và deduplication phân tán.
10. Đo hiệu năng bằng dữ liệu đại diện trước khi tối ưu.
11. Tạo báo cáo accepted/rejected để có thể quan sát chất lượng nguồn dữ liệu.
12. Xây dựng một chương trình Java 17+ có test chạy được ngay.

## 2. Trước tiên: phân biệt các trạng thái nguồn

Không nên gộp tất cả trường hợp “không có dữ liệu” thành một trạng thái.

| Trạng thái | Ví dụ | Ý nghĩa | Hợp đồng nên xác định |
| --- | --- | --- | --- |
| Null source | `source == null` | Không có collection để xử lý | Thường là lỗi hợp đồng, ném exception |
| Empty source | `source.isEmpty()` | Nguồn hợp lệ nhưng không có bản ghi | Trả kết quả rỗng |
| Null row | Danh sách chứa phần tử null | Một record không tồn tại | Reject/skip có lý do |
| Null field | `row.id() == null` | Record tồn tại nhưng thiếu field bắt buộc | Validate và reject hoặc áp dụng business rule |
| Blank field | `""` hoặc chuỗi toàn whitespace | Có string nhưng không có nội dung hữu ích | Reject nếu field bắt buộc |
| Duplicate row | Hai record cùng business key | Nhiều bản ghi đại diện cùng một định danh | Áp dụng duplicate policy |
| Boundary value | `Long.MAX_VALUE` | Giá trị hợp lệ ở biên kiểu dữ liệu | Chấp nhận hoặc reject theo domain range |

**Null source và empty source không tương đương.** Một API nhận `List<T>` có thể quy định null là caller đã vi phạm hợp đồng, còn empty list là kết quả hợp lệ khi query không có row. Nếu tự động đổi null thành empty list, pipeline có thể che lỗi cấu hình, lỗi mapping hoặc thiếu dữ liệu upstream.

### 2.1. Quy ước cho ví dụ trong bài

Chương trình minh họa xử lý một danh sách measurement:

- Null source: ném `NullPointerException` với thông điệp rõ ràng.
- Empty source: trả kết quả rỗng, tổng bằng 0, min/max không có.
- Null record: reject với `NULL_RECORD`.
- Null ID: reject với `NULL_ID`.
- ID rỗng/whitespace: reject với `BLANK_ID`.
- Null value: reject với `NULL_VALUE`.
- Duplicate ID: reject với `DUPLICATE_ID`.
- ID được trim bằng `String.strip()`; phân biệt chữ hoa/chữ thường.
- Với duplicate hợp lệ, **bản ghi hợp lệ đầu tiên thắng**.
- Một bản ghi invalid không chiếm ID; bản ghi hợp lệ phía sau vẫn được nhận.
- Giá trị kiểu long được chấp nhận toàn miền; tổng dùng `BigInteger` để không overflow.
- Kết quả giữ thứ tự input và trả các list không thể sửa đổi.

Đây là một **policy mẫu có chủ đích**, không phải quy tắc chung cho mọi domain. Pipeline sản phẩm phải chọn policy phù hợp với ý nghĩa dữ liệu của mình.

## 3. Thiết kế hợp đồng dữ liệu trước khi viết code

Một pipeline nên mô tả được đầu vào, các bước biến đổi và đầu ra.

```text
Raw source
   |
   v
Source contract check
   |
   v
Record validation
   |
   v
Field normalization
   |
   v
Duplicate detection
   |
   v
Accepted records -----> Aggregate / transform
   |
   +-------------------> Rejected records + reasons
   |
   v
Immutable result / next stage
```

Thứ tự các bước rất quan trọng. Ví dụ, nếu một record có ID hợp lệ nhưng value null, pipeline có nên đánh dấu ID đó đã xuất hiện hay không? Trong policy mẫu, **validation xảy ra trước duplicate detection**. Vì thế record invalid không làm một record valid phía sau bị coi là duplicate.

### 3.1. Lỗi cấp nguồn và lỗi cấp record

Có hai phạm vi lỗi khác nhau:

**Lỗi cấp nguồn/batch** làm pipeline không thể tiếp tục theo hợp đồng, ví dụ source null, source không đọc được, schema không đúng hoặc transaction đã thất bại. Các lỗi này thường cần throw exception hoặc fail batch.

**Lỗi cấp record** chỉ ảnh hưởng một phần tử, ví dụ null row, thiếu ID, value null hoặc duplicate key. Nếu business cho phép partial acceptance, có thể đưa record vào danh sách rejected và tiếp tục xử lý record khác.

Không tự động biến mọi exception thành rejected row. Ví dụ lỗi database connection, lỗi deserialize do schema mismatch hoặc lỗi lập trình không nên bị bỏ qua như một record không hợp lệ bình thường.

### 3.2. Reject có lý do, không chỉ lọc bỏ

Cách dễ viết nhưng khó vận hành:

```java
List<Record> accepted = source.stream()
        .filter(Objects::nonNull)
        .filter(record -> record.id() != null)
        .toList();
```

Code này âm thầm loại record null và record thiếu ID. Sau khi chạy, hệ thống không biết đã loại bao nhiêu record, vì sao bị loại và dữ liệu nào cần sửa.

Một pipeline kiểm thử/production tốt hơn trả cả:

- Danh sách record hợp lệ.
- Danh sách record bị từ chối.
- Vị trí nguồn của record.
- Lý do reject dạng enum/code ổn định.
- Các chỉ số tổng hợp cần thiết.

Không log nguyên record nếu có PII/secrets; có thể ghi source index, reason, correlation ID và một identifier đã được bảo vệ theo policy.

### 3.3. Partial acceptance hay all-or-nothing?

Hai chính sách đều có thể đúng:

| Policy | Hành vi | Dùng khi |
| --- | --- | --- |
| Partial acceptance | Nhận record hợp lệ, reject record lỗi, trả report | Batch import có thể xử lý từng dòng độc lập |
| All-or-nothing | Chỉ commit nếu mọi record đều hợp lệ | Giao dịch nghiệp vụ cần tính nguyên tử |
| Quarantine | Tách record lỗi sang vùng xử lý riêng | Cần sửa/replay dữ liệu sau khi điều tra |
| Fail-fast | Gặp lỗi hợp đồng nghiêm trọng thì dừng | Schema/config/source không đáng tin |

Nếu batch là một giao dịch tài chính phải nguyên tử, không được lấy ví dụ partial acceptance trong bài rồi áp dụng trực tiếp mà không có business approval. Việc chọn policy là một phần của contract, không chỉ là lựa chọn kỹ thuật.

## 4. Null: kiểm thử từng tầng riêng biệt

### 4.1. Null source

```java
List<Measurement> source = null;
process(source); // Hợp đồng ví dụ: ném NullPointerException
```

Nên fail sớm ở boundary bằng `Objects.requireNonNull(source, "...")`. Không chờ đến `source.size()` hoặc iterator để nhận một NPE khó hiểu.

Nếu API muốn chấp nhận null như empty, hãy ghi rõ trong Javadoc và test riêng. Đừng để mỗi caller tự đoán.

### 4.2. Empty source

```java
Result result = process(List.of());

assert result.accepted().isEmpty();
assert result.rejected().isEmpty();
assert result.sum().equals(BigInteger.ZERO);
assert result.min().isEmpty();
assert result.max().isEmpty();
```

Empty source là một kết quả hợp lệ. Khi không có accepted record, min/max phải thể hiện “không có giá trị”, ví dụ `OptionalLong.empty()`. Không trả 0 cho min/max vì 0 có thể là một giá trị thực.

### 4.3. Null row

```java
List<RawMeasurement> rows = Arrays.asList(
        new RawMeasurement("A", 10L),
        null,
        new RawMeasurement("B", 20L)
);
```

`List.of(...)` không chấp nhận phần tử null; dùng `Arrays.asList` hoặc một collection có thể chứa null khi tạo test fixture như trên.

Null row không giống null field. Trong report, phân biệt `NULL_RECORD` và `NULL_ID` để upstream có thể sửa đúng tầng.

### 4.4. Null field và blank field

```java
new RawMeasurement(null, 10L);  // null ID
new RawMeasurement("   ", 10L); // blank ID
new RawMeasurement("A", null);  // null value
new RawMeasurement("A", 0L);    // zero là một giá trị hợp lệ trong demo
```

Không dùng `Objects.toString(value, "0")` hoặc `Optional.ofNullable(value).orElse(0L)` để tự động đổi null thành 0 nếu domain không quy định như vậy. Null có thể có nghĩa thiếu dữ liệu, chưa tính, không áp dụng hoặc lỗi upstream; các ý nghĩa này khác nhau.

### 4.5. Phân biệt null, empty và whitespace trong String

- `null`: không có object String.
- `""`: String có độ dài 0.
- `" "`: có một ký tự space.
- `"\t\n"`: có ký tự whitespace.
- `" A "`: có dữ liệu nhưng bao quanh bởi whitespace.

`String.isBlank()` kiểm tra chuỗi rỗng hoặc chỉ chứa whitespace. `String.strip()` loại bỏ whitespace ở đầu/cuối theo định nghĩa Unicode của Java. Các API này có từ Java 11.

Trong demo, dùng `strip()` rồi kiểm tra `isEmpty()`. Không trim tất cả field text một cách máy móc: khoảng trắng có thể có ý nghĩa trong mật khẩu, mã định danh opaque, nội dung người dùng hoặc protocol payload.

## 5. Duplicate: xác định identity và policy rõ ràng

Deduplication không đơn giản là gọi `distinct()`. Trước tiên cần trả lời: **hai record được coi là cùng một record theo tiêu chí nào?**

### 5.1. Chọn duplicate key

Ví dụ:

```java
record CustomerEvent(
        String eventId,
        String customerId,
        long sequence,
        String payload) {}
```

Nếu `eventId` là unique event identity, dedupe theo eventId. Nếu dedupe theo `customerId`, pipeline có thể vô tình loại các sự kiện khác nhau của cùng customer. Không dùng toàn bộ record equality nếu business identity chỉ là một field.

### 5.2. Chuẩn hóa key trước khi so sánh

Trong demo, `" A "` và `"A"` cùng được chuẩn hóa thành `"A"`, nên là duplicate. `"a"` vẫn là key khác vì policy phân biệt hoa/thường.

Nếu nghiệp vụ không phân biệt case, hãy quy định rõ và dùng locale-independent normalization, ví dụ `toUpperCase(Locale.ROOT)` hoặc `toLowerCase(Locale.ROOT)`. Không dùng default locale của máy chủ để tạo khóa, vì kết quả có thể khác giữa môi trường.

Với ID Unicode, có thể cần Unicode normalization (ví dụ NFC) nếu hai chuỗi có thể biểu diễn cùng ký tự bằng các code-point sequence khác nhau. Chỉ áp dụng khi contract của identifier yêu cầu; không normalize mọi payload.

### 5.3. Các policy duplicate thường gặp

| Policy | Kết quả | Câu hỏi cần quyết định |
| --- | --- | --- |
| First valid wins | Giữ record hợp lệ đầu tiên | Thứ tự nguồn có đáng tin không? |
| Last valid wins | Giữ record hợp lệ cuối cùng | Có cần giữ vị trí ban đầu hay vị trí cuối? |
| Reject all duplicates | Nếu key lặp, loại cả nhóm | Có cần xử lý cả record đầu tiên sau khi phát hiện lặp? |
| Aggregate | Gộp các record cùng key | Phép gộp có associative/commutative không? |
| Conflict | Duplicate có payload khác nhau là lỗi | Cần đối chiếu source/version nào? |

Không có policy đúng cho mọi dữ liệu. Ví dụ trong event ingestion, first-wins có thể phù hợp nếu nguồn được sắp theo thứ tự đáng tin; với snapshot import, last-wins có thể đúng nếu có version/time ordering rõ.

### 5.4. Duplicate phải được kiểm tra sau validation

Giả sử đầu vào:

```text
index 0: ID=A, value=null
index 1: ID=A, value=10
```

Nếu duplicate detection chạy trước validation và đánh dấu ID A ngay ở index 0, record hợp lệ ở index 1 sẽ bị loại. Trong ví dụ này, record invalid không chiếm key; record valid ở index 1 được nhận.

Nếu nghiệp vụ yêu cầu mọi lần xuất hiện của một key đều làm cả nhóm bị loại, cần thiết kế policy khác, có thể cần hai lượt hoặc group-by. Không thể đạt policy đó bằng first-valid-wins một lượt mà không thay đổi logic.

### 5.5. Vì sao stream distinct có thể không đủ?

```java
source.stream().distinct().toList();
```

`distinct()` dựa trên `equals/hashCode` của object. Nó không tự biết business key cần dedupe là gì. Nếu record chứa field khác nhau nhưng cùng ID, chúng vẫn có thể không được loại. Nếu `equals` được override theo ID, thay đổi domain equality chỉ để phục vụ một pipeline cũng có thể gây side effects ở nơi khác.

Dùng một `Set` theo business key thường thể hiện policy rõ hơn.

## 6. Dữ liệu biên: giá trị hợp lệ ở ranh giới và giá trị vượt ranh giới

### 6.1. Integer và Long

Các giá trị cần test:

| Kiểu | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: |
| `int` | `Integer.MIN_VALUE` | `Integer.MAX_VALUE` |
| `long` | `Long.MIN_VALUE` | `Long.MAX_VALUE` |

Đừng chỉ test 0, 1 và -1. Bug overflow thường chỉ xuất hiện gần giới hạn.

```java
long max = Long.MAX_VALUE;
long overflow = max + 1;
System.out.println(overflow);
```

Phép cộng primitive long **wrap around** theo two's complement; nó không tự ném exception khi overflow. Nếu overflow phải là lỗi:

```java
long total = Math.addExact(a, b);
```

Nếu tổng có thể vượt miền long nhưng vẫn là kết quả hợp lệ, dùng `BigInteger`:

```java
BigInteger total = BigInteger.valueOf(a)
        .add(BigInteger.valueOf(b));
```

Demo chọn `BigInteger` để có tổng chính xác mà không phải reject batch chỉ vì aggregate vượt long.

### 6.2. Decimal và tiền tệ

Với dữ liệu cần số thập phân chính xác, test `BigDecimal` theo cả giá trị và scale:

```java
BigDecimal a = new BigDecimal("10.20");
BigDecimal b = new BigDecimal("10.2");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
```

`compareTo` so sánh giá trị số; `equals` còn xét scale. Nếu scale là một phần contract (ví dụ tiền tệ 2 chữ số thập phân), hãy test đúng scale. Tránh dùng `new BigDecimal(0.1)` vì double đã mang biểu diễn nhị phân gần đúng; dùng string hoặc integer minor units theo domain.

Kiểm tra:
- Giá trị 0 và -0 nếu format nguồn phân biệt.
- Giá trị âm/dương sát giới hạn precision.
- Scale nhỏ hơn, bằng và lớn hơn scale cho phép.
- Làm tròn/truncate theo business policy.
- Chuỗi decimal sai định dạng, exponent hoặc locale-specific decimal separator.
- Giá trị vượt precision của database column.

### 6.3. Ngày giờ

Các boundary hữu ích:

- Ngày cuối tháng và ngày đầu tháng kế tiếp.
- Năm nhuận: 29/02 và năm không nhuận.
- Cuối năm/đầu năm.
- Midnight và cuối ngày.
- Timestamp có fractional seconds sát precision của storage.
- Time zone transition và DST gap/overlap khi domain có zone.
- Giá trị ngoài miền mà database hoặc protocol hỗ trợ.

Dùng `LocalDate` cho ngày lịch, `Instant` cho thời điểm tuyệt đối, `OffsetDateTime` khi cần offset và `ZonedDateTime` khi cần quy tắc vùng. Không tự đổi LocalDateTime thành Instant mà không có zone policy.

### 6.4. String, Unicode và giới hạn kích thước

Test các trường hợp:
- Empty string, whitespace-only, leading/trailing spaces.
- Chuỗi dài đúng giới hạn và vượt giới hạn một ký tự.
- Ký tự tiếng Việt có dấu.
- Ký tự supplementary Unicode dùng surrogate pair.
- Hai cách mã hóa Unicode tương đương về mặt hiển thị.
- Control characters và ký tự không được phép theo protocol.

Không cắt chuỗi theo byte count nếu giới hạn là Unicode code points hoặc UTF-16 units. Xác định đơn vị giới hạn trước khi validate.

### 6.5. Parsing ngoài miền

Nếu nhận numeric string:

```java
long value = Long.parseLong(input);
```

`Long.parseLong` ném `NumberFormatException` nếu input null, rỗng, sai định dạng hoặc vượt miền long. Hãy phân loại parse failure rõ ràng. Đừng bắt exception rồi tự gán 0.

Nếu input là JSON, phân biệt field vắng mặt với field có giá trị null và field có giá trị 0. Tầng deserialization phải giữ được khác biệt này nếu business cần.

## 7. Pipeline một lượt: validation, normalization, dedup và aggregate

Một cách triển khai hiệu quả cho danh sách vừa/nhỏ:

1. Kiểm tra source không null.
2. Duyệt mỗi phần tử đúng một lần.
3. Validate record và field bắt buộc.
4. Normalize business key theo contract.
5. Kiểm tra duplicate key bằng Set.
6. Nếu hợp lệ và chưa thấy key, thêm vào accepted.
7. Cập nhật aggregate trong cùng lượt.
8. Nếu invalid/duplicate, thêm một rejection với reason.
9. Trả result bất biến.

Độ phức tạp kỳ vọng:
- Thời gian: `O(n)` với HashSet có hash distribution phù hợp.
- Bộ nhớ: `O(u + r)`, với `u` là số accepted unique keys và `r` là số rejected rows.

Danh sách accepted giữ thứ tự nguồn vì code append theo thứ tự input; HashSet chỉ dùng để tra cứu, không dùng để xuất kết quả.

### 7.1. Vì sao không dùng indexed get trên mọi List?

`ArrayList.get(index)` có chi phí truy cập gần như hằng số, nhưng `LinkedList.get(index)` phải đi qua node. Một vòng lặp `for (int i=0; i<list.size(); i++) list.get(i)` trên LinkedList có thể thành `O(n²)`.

Dùng enhanced-for/iterator như ví dụ sẽ duyệt tuyến tính cho cả ArrayList và LinkedList.

### 7.2. Đừng tạo nhiều intermediate collections không cần thiết

Một chuỗi `filter().map().distinct().sorted().collect()` có thể tạo thêm object/collection và nhiều lần duyệt. Stream API vẫn rất hữu ích khi pipeline biểu đạt rõ và có profiling xác nhận hiệu quả; nhưng khi cần stateful dedup, rejection diagnostics và aggregate trong một lượt, loop rõ ràng có thể đơn giản và hiệu quả hơn.

Không tối ưu chỉ dựa trên số dòng code. Đo trên dataset đại diện.

## 8. Chương trình Java 17+ hoàn chỉnh

Ví dụ dùng một measurement pipeline. Policy đã chọn:

- Null source là lỗi hợp đồng.
- Empty source là kết quả hợp lệ.
- Null row/field và blank ID bị reject.
- ID được strip, phân biệt hoa/thường.
- Duplicate hợp lệ đầu tiên thắng.
- Invalid row không chiếm duplicate key.
- Long.MIN_VALUE và Long.MAX_VALUE được chấp nhận.
- Tổng dùng BigInteger.
- Accepted/rejected lists là immutable.
- Source index là zero-based.

Tạo file **`DataPipelineDemo.java`**:

```java
import java.math.BigInteger;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.OptionalLong;
import java.util.Set;

public class DataPipelineDemo {
    record RawMeasurement(String id, Long value) {}

    record Measurement(String id, long value, int sourceIndex) {}

    enum RejectReason {
        NULL_RECORD,
        NULL_ID,
        BLANK_ID,
        NULL_VALUE,
        DUPLICATE_ID
    }

    record RejectedRow(
            int sourceIndex,
            String id,
            RejectReason reason) {}

    record Result(
            List<Measurement> accepted,
            List<RejectedRow> rejected,
            BigInteger sum,
            OptionalLong min,
            OptionalLong max) {
        Result {
            accepted = List.copyOf(accepted);
            rejected = List.copyOf(rejected);
            Objects.requireNonNull(sum);
            Objects.requireNonNull(min);
            Objects.requireNonNull(max);
        }
    }

    static Result process(List<RawMeasurement> source) {
        Objects.requireNonNull(source, "source must not be null");

        List<Measurement> accepted = new ArrayList<>();
        List<RejectedRow> rejected = new ArrayList<>();
        Set<String> seenIds = new HashSet<>();

        BigInteger sum = BigInteger.ZERO;
        long min = Long.MAX_VALUE;
        long max = Long.MIN_VALUE;
        int index = 0;

        for (RawMeasurement row : source) {
            int sourceIndex = index++;

            if (row == null) {
                rejected.add(new RejectedRow(
                        sourceIndex, null, RejectReason.NULL_RECORD));
                continue;
            }

            if (row.id() == null) {
                rejected.add(new RejectedRow(
                        sourceIndex, null, RejectReason.NULL_ID));
                continue;
            }

            String id = row.id().strip();
            if (id.isEmpty()) {
                rejected.add(new RejectedRow(
                        sourceIndex, id, RejectReason.BLANK_ID));
                continue;
            }

            if (row.value() == null) {
                rejected.add(new RejectedRow(
                        sourceIndex, id, RejectReason.NULL_VALUE));
                continue;
            }

            if (!seenIds.add(id)) {
                rejected.add(new RejectedRow(
                        sourceIndex, id, RejectReason.DUPLICATE_ID));
                continue;
            }

            long value = row.value();
            accepted.add(new Measurement(id, value, sourceIndex));

            sum = sum.add(BigInteger.valueOf(value));
            min = Math.min(min, value);
            max = Math.max(max, value);
        }

        return new Result(
                accepted,
                rejected,
                sum,
                accepted.isEmpty()
                        ? OptionalLong.empty()
                        : OptionalLong.of(min),
                accepted.isEmpty()
                        ? OptionalLong.empty()
                        : OptionalLong.of(max));
    }

    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    static void expectThrows(
            Class<? extends Throwable> type,
            Runnable action,
            String label) {
        try {
            action.run();
        } catch (Throwable error) {
            if (type.isInstance(error)) {
                return;
            }
            throw new AssertionError(
                    label + ": wrong exception " + error, error);
        }

        throw new AssertionError(
                label + ": expected " + type.getSimpleName());
    }

    static void runTests() {
        // 1. Null source violates the method contract.
        expectThrows(
                NullPointerException.class,
                () -> process(null),
                "null source is distinct from empty source");

        // 2. Empty source is valid and has no min/max.
        Result empty = process(List.of());
        check(empty.accepted().isEmpty(), "empty accepted");
        check(empty.rejected().isEmpty(), "empty rejected");
        check(empty.sum().equals(BigInteger.ZERO), "empty sum");
        check(
                empty.min().isEmpty() && empty.max().isEmpty(),
                "empty bounds");

        // 3. Mixed records cover null, blank, duplicate and boundaries.
        List<RawMeasurement> mixed = Arrays.asList(
                null,
                new RawMeasurement(null, 1L),
                new RawMeasurement("  ", 2L),
                new RawMeasurement("bad-value", null),
                new RawMeasurement(" A ", 7L),
                new RawMeasurement("A", 99L),
                new RawMeasurement("B", Long.MIN_VALUE),
                new RawMeasurement("C", Long.MAX_VALUE),
                new RawMeasurement("a", 3L)
        );

        Result result = process(mixed);

        check(result.accepted().size() == 4, "accepted count");
        check(result.rejected().size() == 5, "rejected count");
        check(result.accepted().get(0).id().equals("A"), "trimmed id");
        check(result.accepted().get(0).value() == 7L, "first valid wins");
        check(result.accepted().get(0).sourceIndex() == 4, "source index");
        check(
                result.accepted().get(1).value() == Long.MIN_VALUE,
                "long min");
        check(
                result.accepted().get(2).value() == Long.MAX_VALUE,
                "long max");
        check(result.accepted().get(3).id().equals("a"), "case-sensitive ids");

        check(
                result.sum().equals(BigInteger.valueOf(9L)),
                "overflow-safe sum");
        check(
                result.min().orElseThrow() == Long.MIN_VALUE,
                "minimum");
        check(
                result.max().orElseThrow() == Long.MAX_VALUE,
                "maximum");

        check(
                result.rejected().get(0).reason() == RejectReason.NULL_RECORD,
                "null record");
        check(
                result.rejected().get(1).reason() == RejectReason.NULL_ID,
                "null id");
        check(
                result.rejected().get(2).reason() == RejectReason.BLANK_ID,
                "blank id");
        check(
                result.rejected().get(3).reason() == RejectReason.NULL_VALUE,
                "null value");
        check(
                result.rejected().get(4).reason() == RejectReason.DUPLICATE_ID,
                "duplicate");

        // 4. An invalid row must not reserve an ID.
        Result invalidThenValid = process(Arrays.asList(
                new RawMeasurement("X", null),
                new RawMeasurement("X", 10L)
        ));
        check(
                invalidThenValid.accepted().size() == 1,
                "invalid row does not reserve id");
        check(
                invalidThenValid.accepted().get(0).value() == 10L,
                "valid after invalid");

        // 5. Aggregate can exceed long without wrapping.
        Result overflowSafe = process(List.of(
                new RawMeasurement("max", Long.MAX_VALUE),
                new RawMeasurement("one", 1L)
        ));
        check(
                overflowSafe.sum().equals(
                        BigInteger.valueOf(Long.MAX_VALUE)
                                .add(BigInteger.ONE)),
                "sum exceeds long without overflow");

        // 6. Returned collections cannot be modified.
        expectThrows(
                UnsupportedOperationException.class,
                () -> result.accepted().add(
                        new Measurement("Z", 1L, 99)),
                "accepted list immutable");
        expectThrows(
                UnsupportedOperationException.class,
                () -> result.rejected().clear(),
                "rejected list immutable");

        System.out.println("nullSourceRejected=true");
        System.out.println("emptySourceAccepted=0");
        System.out.println("accepted=" + result.accepted().size());
        System.out.println("rejected=" + result.rejected().size());
        System.out.println("firstValidDuplicatePolicy=first-wins");
        System.out.println("normalizedId=A");
        System.out.println("sum=" + result.sum());
        System.out.println("min=" + result.min().orElseThrow());
        System.out.println("max=" + result.max().orElseThrow());
        System.out.println("longOverflowSafe=true");
        System.out.println("immutableResults=true");
        System.out.println("ALL CHECKS PASSED");
    }

    public static void main(String[] args) {
        runTests();
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac DataPipelineDemo.java
java DataPipelineDemo
```

Stdout đã kiểm chứng:

```text
nullSourceRejected=true
emptySourceAccepted=0
accepted=4
rejected=5
firstValidDuplicatePolicy=first-wins
normalizedId=A
sum=9
min=-9223372036854775808
max=9223372036854775807
longOverflowSafe=true
immutableResults=true
ALL CHECKS PASSED
```

### 8.1. Giải thích thiết kế

`RawMeasurement` giữ ID và giá trị nullable. Dùng `Long` thay vì primitive `long` để biểu diễn được null từ source.

`Measurement` là record hợp lệ sau khi normalize ID. `sourceIndex` giúp truy ngược vị trí trong batch đầu vào.

`RejectReason` là enum để downstream có thể thống kê hoặc xử lý theo mã ổn định. Không nên chỉ lưu message exception tùy ý làm reason code.

`HashSet` lưu các ID đã nhận. `seenIds.add(id)` trả true ở lần đầu và false khi ID đã xuất hiện. HashSet chỉ phục vụ lookup; accepted list được append theo input order.

`BigInteger` cộng chính xác toàn miền long. `OptionalLong` thể hiện min/max không có giá trị khi accepted list rỗng.

`List.copyOf` tạo các list không thể sửa đổi từ bên ngoài. Các phần tử trong ví dụ là record bất biến với field kiểu immutable.

### 8.2. Vì sao loop dùng enhanced-for?

Enhanced-for sử dụng iterator. Với List như LinkedList, nó tránh gọi `get(index)` lặp đi lặp lại có thể làm độ phức tạp tăng lên O(n²). Biến index chỉ dùng lưu source position, không dùng truy cập list theo vị trí.

### 8.3. Vì sao không parallelStream?

Policy first-valid-wins phụ thuộc thứ tự nguồn. Dùng một HashSet chia sẻ trong parallel stream không an toàn; dùng concurrent set lại có thể làm record thắng phụ thuộc vào thread timing. Nếu cần parallel, phải thiết kế partitioning và merge policy sao cho kết quả vẫn deterministic.

## 9. Ma trận test cho nguồn rỗng, null, duplicate và boundary

Một test matrix nên ghi input, expected behavior và lý do. Ví dụ:

| Nhóm | Input | Kết quả mong đợi |
| --- | --- | --- |
| Null source | source = null | Ném exception theo contract |
| Empty source | empty list | accepted/rejected rỗng, sum 0, min/max empty |
| Null row | phần tử null | Reject NULL_RECORD |
| Null ID | record.id null | Reject NULL_ID |
| Blank ID | `""`, `" "`, `"\t"` | Reject BLANK_ID |
| Null value | value null | Reject NULL_VALUE |
| Zero | value = 0 | Chấp nhận nếu domain cho phép |
| Negative | value < 0 | Chấp nhận/reject theo domain range |
| Duplicate exact | cùng ID hai lần | Theo duplicate policy |
| Duplicate normalized | `" A "` và `"A"` | Duplicate trong demo |
| Case variant | `"A"` và `"a"` | Khác nhau trong demo |
| Invalid then valid | ID X/null value, sau đó X/10 | Record hợp lệ được nhận |
| Long lower bound | `Long.MIN_VALUE` | Không overflow khi đọc |
| Long upper bound | `Long.MAX_VALUE` | Không overflow khi đọc |
| Aggregate overflow | Long.MAX_VALUE + 1 | BigInteger giữ chính xác |
| No accepted rows | mọi row bị reject | min/max empty, sum 0 |
| Result immutability | sửa accepted/rejected | UnsupportedOperationException |

Không chỉ kiểm tra tổng số accepted/rejected. Nên xác nhận **record nào** được nhận, **record nào** bị reject và reason/index tương ứng.

### 9.1. Test duplicate phải xác định thứ tự

Với first-valid-wins:

```text
[A:10, A:20] -> giữ A:10
[A:20, A:10] -> giữ A:20
```

Hai input có cùng tập record nhưng thứ tự khác nhau có thể tạo kết quả khác. Đây là semantics của policy, cần test rõ. Nếu muốn kết quả không phụ thuộc input order, cần một tie-breaker deterministic như version hoặc event timestamp, không nên để thread scheduling quyết định.

### 9.2. Test boundary của aggregate

Với primitive long:

```java
long a = Long.MAX_VALUE;
long b = 1L;
long total = Math.addExact(a, b); // ArithmeticException
```

Nếu dùng `Math.addExact`, test phải xác nhận overflow được báo lỗi đúng như contract. Nếu dùng BigInteger như demo, test xác nhận tổng lớn hơn Long.MAX_VALUE được giữ nguyên.

### 9.3. Test empty và null riêng biệt

Đừng viết một test duy nhất “no data” rồi truyền cả null và empty. Hai trạng thái có thể mang ý nghĩa vận hành khác nhau. Test riêng để bảo đảm không có thay đổi contract âm thầm.

## 10. Property-based và invariant testing

Ngoài các ví dụ cố định, pipeline có thể kiểm tra những invariant luôn phải đúng với mọi input.

### 10.1. Unique accepted IDs

Sau khi normalize:

```java
Set<String> ids = new HashSet<>();
for (Measurement row : result.accepted()) {
    check(ids.add(row.id()), "accepted IDs must be unique");
}
```

### 10.2. Accepted/rejected phải giải thích toàn bộ input

Nếu policy phân loại mỗi source position đúng một lần:

```text
acceptedCount + rejectedCount == sourceCount
```

Không có record nào biến mất khỏi report. Nếu pipeline có thêm trạng thái ignored/deferred, hãy đưa chúng vào accounting riêng để tổng vẫn khớp.

### 10.3. Aggregate phải khớp accepted rows

```java
BigInteger expected = result.accepted().stream()
        .map(row -> BigInteger.valueOf(row.value()))
        .reduce(BigInteger.ZERO, BigInteger::add);

check(expected.equals(result.sum()), "aggregate invariant");
```

Đây là test độc lập để so sánh aggregate của pipeline với cách tính tham chiếu. Dù implementation chính dùng loop, test có thể dùng một cách biểu đạt khác để giảm nguy cơ lặp lại cùng bug.

### 10.4. Tính ổn định và deterministic

Với cùng input và cùng policy, kết quả phải giống nhau:
- accepted IDs/order.
- rejected indexes/reasons.
- aggregate.
- min/max.
- normalized keys.

Nếu kết quả thay đổi giữa các lần chạy, kiểm tra HashMap iteration order, parallel processing, current time, default locale, random values hoặc external state.

### 10.5. Metamorphic tests

Có thể kiểm tra các quan hệ khi biến đổi input:

- Thêm một null row vào cuối: accepted không đổi, rejected tăng một với NULL_RECORD.
- Thêm một duplicate hợp lệ ở cuối: accepted không đổi, rejected tăng một với DUPLICATE_ID.
- Thêm một record hợp lệ có ID mới: accepted tăng một và aggregate đổi đúng value.
- Thêm một record invalid có ID trùng với record hợp lệ: theo policy demo, nó bị reject do validation và không thay record hợp lệ.
- Đảo thứ tự hai duplicate: first-wins chọn record xuất hiện trước theo thứ tự mới.

Những invariant này thường phát hiện lỗi mà vài test example không thấy.

## 11. Tích hợp vào test framework

Chương trình demo dùng assertion tự viết để chạy bằng JDK 17+ không cần dependency. Trong project thực tế, có thể chuyển từng case thành unit tests bằng test framework đang được dự án duy trì và tương thích JDK mục tiêu.

Nên chia test theo trách nhiệm:
- `process_nullSource_throws`.
- `process_emptySource_returnsEmptyResult`.
- `process_nullRow_recordsRejectReason`.
- `process_duplicateId_keepsFirstValidRecord`.
- `process_longBoundaries_usesExactAggregate`.
- `process_resultLists_areImmutable`.

Một test nên kiểm tra một hành vi chính. Khi failure xảy ra, tên test và assertion phải chỉ ra policy nào bị phá vỡ.

### 11.1. Unit test không thay integration test

Unit tests kiểm tra logic pipeline với input đã kiểm soát. Integration tests cần kiểm tra boundary thật:
- Database trả null, duplicate hoặc numeric boundary ra sao.
- JSON/CSV parser phân biệt missing/null/empty thế nào.
- Message broker redelivery có tạo duplicate không.
- Transaction commit/rollback khi batch partial fail.
- Encoding, timezone và decimal scale của external source.

Nếu nguồn là database, test query/order phải deterministic. Nếu source không đảm bảo order, first-wins có thể không deterministic giữa các lần query; cần tie-breaker như sequence/version.

### 11.2. Fixture phải cho phép tạo null

`List.of` không cho phép null elements. Với test cần null row, dùng `Arrays.asList` hoặc mutable list phù hợp. Đây là chi tiết nhỏ nhưng thường khiến test không tạo được trường hợp cần kiểm tra.

### 11.3. Không dựa vào Java assert để test mặc định

Từ khóa `assert` trong Java chỉ được thực thi khi JVM bật assertions bằng `-ea`. Demo dùng helper `check` ném AssertionError để mọi test luôn chạy khi gọi `java DataPipelineDemo`. Trong JUnit hoặc test framework tương tự, dùng assertion APIs của framework.

## 12. Tối ưu pipeline đúng cách

### 12.1. Một lượt duyệt

Khi có thể, validate, normalize, dedupe và aggregate trong cùng một vòng lặp. Tránh:
1. Duyệt để lọc.
2. Duyệt lần nữa để normalize.
3. Duyệt lần nữa để distinct.
4. Duyệt lần nữa để aggregate.
5. Duyệt lần nữa để thống kê.

Nhiều lượt không luôn sai — đôi khi cần thiết cho all-or-nothing hoặc sort/group policy — nhưng phải có lý do.

### 12.2. Chọn cấu trúc dữ liệu theo semantics

| Nhu cầu | Cấu trúc phù hợp |
| --- | --- |
| Kiểm tra key đã xuất hiện | HashSet |
| Map key → record thắng | HashMap/LinkedHashMap tùy thứ tự cần giữ |
| Giữ accepted theo input order | ArrayList append theo lượt duyệt |
| Queue có backpressure | BlockingQueue hoặc cơ chế reactive phù hợp |
| Tổng số nguyên lớn | BigInteger |
| Số thập phân chính xác | BigDecimal |
| Min/max có thể không tồn tại | OptionalLong hoặc Optional<T> |

Không dùng TreeSet chỉ để dedupe nếu không cần sorting; thao tác thường là O(log n) thay vì expected O(1) của HashSet. Nhưng nếu thứ tự sorted là yêu cầu thật, TreeSet hoặc sort có thể phù hợp hơn.

### 12.3. Pre-size chỉ khi có ước lượng đáng tin

Nếu source có kích thước đã biết và hợp lý, có thể tạo ArrayList/HashSet với capacity phù hợp để giảm resize. Không cấp một array cực lớn chỉ vì metadata báo batch có thể lớn; việc pre-size quá tay làm tăng memory pressure.

Tối ưu capacity cần cân nhắc load factor, số unique keys thực tế và heap budget. Nếu không có số liệu, dùng defaults trước rồi đo.

### 12.4. Không tạo object thừa

Các object rejection/measurement giúp diagnostics rõ, nhưng với throughput rất cao có thể tăng allocation. Trước khi bỏ chúng:
- Đo allocation rate bằng profiler/JFR.
- Xác định report cần giữ record-level hay chỉ reason counts.
- Nếu chỉ cần counts, có thể cấu hình chế độ metrics-only.
- Nếu cần quarantine/replay, phải giữ đủ thông tin record theo policy.

Không hy sinh khả năng điều tra dữ liệu chỉ để giảm vài object mà chưa đo.

### 12.5. Dùng primitive specialization khi có bằng chứng

Primitive collections hoặc specialized libraries có thể giảm boxing, nhưng chỉ thêm dependency nếu bottleneck đã được đo. Trong demo, `Long` là wrapper vì cần biểu diễn null. Nếu schema guarantee không null, model có thể dùng long primitive ở tầng đã validate.

### 12.6. Tránh sort nếu không cần

Nếu mục tiêu chỉ giữ record đầu tiên theo input order, một HashSet + append list là đủ. Sort toàn bộ input trước khi dedupe làm tăng thời gian và memory, đồng thời có thể thay đổi semantics. Chỉ sort khi domain yêu cầu thứ tự cụ thể.

## 13. Parallel và distributed pipeline

### 13.1. Stateful dedupe không tự parallel-safe

Mẫu này không an toàn khi dùng một Set mutable chung trong parallel stream:

```java
Set<String> seen = new HashSet<>();

source.parallelStream()
        .filter(row -> seen.add(row.id()))
        .toList();
```

`HashSet` không thread-safe. Ngay cả khi đổi sang concurrent set, record thắng có thể phụ thuộc thread scheduling và không còn first-wins theo input order.

### 13.2. Khi cần parallel, tách partition và merge deterministic

Một hướng tổng quát:

1. Normalize và validate theo từng partition.
2. Tính duplicate key cùng source sequence/index.
3. Group theo key.
4. Chọn winner bằng comparator deterministic, ví dụ sequence nhỏ nhất hoặc version mới nhất.
5. Merge kết quả và sort theo output order yêu cầu.
6. Tính aggregate bằng phép gộp có tính associative và không overflow.

Cần xem xét memory/shuffle cost; parallel không mặc định nhanh hơn một vòng lặp tuyến tính.

### 13.3. Dedup qua nhiều batch

HashSet trong một lần gọi process chỉ dedupe trong batch đó. Nếu cùng event ID xuất hiện ở batch kế tiếp, pipeline mới sẽ không biết.

Các cách xử lý:
- Persistent unique constraint trong database.
- Idempotency key được lưu theo thời hạn nghiệp vụ.
- Durable dedupe store.
- Windowed dedup nếu domain chỉ yêu cầu uniqueness trong một khoảng thời gian.
- Partition key + sequence nếu nguồn có thứ tự và contract rõ.

Đừng tuyên bố “đã dedupe” nếu thực tế chỉ dedupe trong một batch.

### 13.4. Idempotency và duplicate là hai vấn đề liên quan nhưng khác nhau

Duplicate detection phát hiện cùng identity xuất hiện nhiều lần. Idempotency bảo đảm chạy lại cùng operation không gây side effect lặp. Một pipeline có thể dedupe input nhưng vẫn tạo duplicate output nếu retry ghi database sau timeout. Dùng idempotency key/unique constraint/transaction phù hợp ở boundary side effect.

### 13.5. Backpressure và bounded memory

Nếu nguồn lớn hơn RAM:
- Đọc theo page/batch hoặc stream có backpressure.
- Không materialize toàn bộ source nếu không cần.
- Giữ dedupe state đúng phạm vi nghiệp vụ; nếu global, state cũng có thể rất lớn.
- Ghi accepted/rejected theo batch với transaction/retry rõ.
- Đảm bảo batch retry không ghi lặp side effects.
- Theo dõi queue depth và processing lag.

Chunking làm giảm memory cho records, nhưng không tự giải quyết dedupe toàn cục nếu Set vẫn phải giữ mọi key đã thấy.

## 14. Các lỗi phổ biến và cách tránh

### Lỗi 1. Coi null source và empty source là một

Có thể che lỗi upstream. **Sửa:** xác định null là exception hay empty theo API contract và test riêng.

### Lỗi 2. Dùng List.of để tạo fixture có null

List.of ném NullPointerException ngay khi tạo fixture. **Sửa:** dùng Arrays.asList hoặc collection phù hợp.

### Lỗi 3. Filter null row mà không ghi nhận

Record biến mất khỏi report. **Sửa:** reject với reason và source index.

### Lỗi 4. Gộp null field thành giá trị mặc định

Null có thể mang nghĩa thiếu dữ liệu. **Sửa:** validate hoặc áp dụng default chỉ khi business rule cho phép.

### Lỗi 5. Dùng isEmpty thay cho isBlank

Chuỗi chỉ chứa spaces/tabs vẫn qua kiểm tra. **Sửa:** dùng strip/isBlank khi contract yêu cầu whitespace-only là blank.

### Lỗi 6. Trim mọi String

Có thể thay đổi payload, password hoặc opaque identifiers. **Sửa:** chỉ normalize field nào có quy tắc rõ.

### Lỗi 7. Dùng default locale để lowercase ID

Kết quả có thể khác giữa môi trường. **Sửa:** Locale.ROOT nếu policy thực sự case-insensitive.

### Lỗi 8. Dedupe theo toàn bộ record equality

Các record cùng business ID nhưng field khác vẫn có thể không bị coi là duplicate. **Sửa:** dùng business key riêng.

### Lỗi 9. Dedupe trước validation

Record invalid có thể chiếm key và làm record hợp lệ sau đó bị loại. **Sửa:** xác định thứ tự stage theo policy; demo validate trước.

### Lỗi 10. Không định nghĩa first-wins/last-wins

Kết quả phụ thuộc implementation hoặc thứ tự đầu vào ngoài dự kiến. **Sửa:** ghi policy và test cả khi đảo input order.

### Lỗi 11. Dùng HashSet iteration để tạo output

HashSet không cam kết thứ tự output theo input. **Sửa:** giữ accepted trong list hoặc collection có order contract.

### Lỗi 12. Dùng parallelStream với HashSet mutable

Data race và nondeterministic winner. **Sửa:** dùng sequential pipeline hoặc thiết kế partition/merge deterministic.

### Lỗi 13. Dùng get(i) trên LinkedList

Có thể biến vòng lặp thành O(n²). **Sửa:** dùng iterator/enhanced-for.

### Lỗi 14. Cộng long mà không kiểm tra overflow

Primitive overflow không tự throw. **Sửa:** Math.addExact hoặc BigInteger.

### Lỗi 15. Dùng double cho tiền tệ

Binary floating point không biểu diễn chính xác nhiều decimal fractions. **Sửa:** BigDecimal hoặc integer minor units.

### Lỗi 16. Trả min/max = 0 khi không có record

0 có thể là dữ liệu thật. **Sửa:** OptionalLong.empty hoặc Optional.empty.

### Lỗi 17. Không giữ source index

Khó truy ngược dữ liệu lỗi trong file/batch. **Sửa:** lưu index/line number/offset hoặc source correlation ID.

### Lỗi 18. Catch mọi exception và tiếp tục

Có thể che bug, mất kết nối hoặc lỗi hạ tầng. **Sửa:** chỉ chuyển lỗi record-level đã phân loại thành rejection; propagate lỗi batch/system.

### Lỗi 19. Chỉ test số lượng accepted

Có thể giữ nhầm record nhưng count vẫn đúng. **Sửa:** assert identity, value, source index, rejection reason và order.

### Lỗi 20. Chỉ test một duplicate order

First-wins và last-wins có thể trùng kết quả trong một case. **Sửa:** test đảo thứ tự và test invalid-before-valid.

### Lỗi 21. Dedupe chỉ trong một batch nhưng nghĩ là global

Duplicate ở batch sau vẫn lọt. **Sửa:** persistent idempotency/dedupe state theo scope.

### Lỗi 22. Chunking nhưng reset seen set mỗi chunk

Duplicate giữa hai chunk không được phát hiện. **Sửa:** giữ state đúng window/global scope hoặc dùng storage bền vững.

### Lỗi 23. Dùng timestamp làm tie-breaker mà không xử lý bằng nhau

Hai event có cùng timestamp vẫn không có thứ tự deterministic. **Sửa:** thêm sequence hoặc stable secondary key.

### Lỗi 24. Benchmark bằng một lần System.nanoTime

JIT warmup, GC và máy chạy khác có thể làm số đo sai. **Sửa:** dùng benchmark framework như JMH, nhiều forks/warmups và dataset đại diện.

### Lỗi 25. Tối ưu trước khi có profile

Có thể tối ưu phần không phải bottleneck. **Sửa:** đo CPU, allocation, GC, I/O và latency trước.

## 15. Đo hiệu năng và xác nhận tối ưu

Pipeline cần đánh giá cả correctness lẫn performance. Một benchmark có ý nghĩa nên thay đổi các đặc tính dữ liệu:

- Batch nhỏ/vừa/lớn.
- Tỷ lệ null row và null field.
- Tỷ lệ duplicate thấp/cao.
- ID ngắn/dài, phân bố hash khác nhau.
- Nhiều record hợp lệ và nhiều record bị reject.
- Giá trị numeric thường và boundary.
- ArrayList và LinkedList nếu API chấp nhận cả hai.
- Cold start và steady state.

### 15.1. Chỉ số nên theo dõi

| Metric | Ý nghĩa |
| --- | --- |
| Input rows/sec | Tốc độ đọc/xử lý |
| Accepted rows/sec | Throughput record hợp lệ |
| Rejected rows by reason | Chất lượng dữ liệu và lỗi upstream |
| Duplicate rate | Tỷ lệ event/record lặp |
| p50/p95/p99 latency | Độ trễ theo phân vị |
| Allocation rate | Số byte/object được cấp phát |
| GC pause/time | Chi phí garbage collection |
| Heap/retained set size | Bộ nhớ bị giữ bởi dedupe state và output |
| Queue depth/lag | Backpressure và độ trễ pipeline |

Không chỉ nhìn tổng thời gian trung bình. p99 có thể xấu do batch có duplicate state lớn hoặc input chứa chuỗi dài.

### 15.2. JMH và profiling

Dùng JMH để microbenchmark những lựa chọn như loop vs stream, HashSet sizing, normalization hoặc cách aggregate. Benchmark nên có warmup, measurement iterations và forks; không tự viết một vòng lặp nanoTime rồi kết luận cho production.

Dùng Java Flight Recorder (JFR) hoặc profiler phù hợp để tìm allocation, CPU hot spots, lock contention và GC. Benchmark micro không thay integration/performance tests trên môi trường deployment.

### 15.3. Tối ưu phải giữ nguyên contract

Sau khi đổi implementation, chạy lại:
- Test null/empty.
- Test duplicate policy.
- Test boundary/overflow.
- Test ordering/determinism.
- Test rejection accounting.
- Test immutability.
- Test idempotency nếu có side effects.

Nếu tối ưu làm thay đổi winner hoặc bỏ qua rejection, đó là thay đổi behavior chứ không phải tối ưu tương đương.

## 16. Bài tập thực hành và đáp án

**Bài 1.** Null source và empty source khác nhau thế nào?  
**Đáp án:** Null source không có collection, thường vi phạm contract; empty source là collection hợp lệ không có phần tử.

**Bài 2.** Vì sao List.of(null) không dùng được để tạo test fixture?  
**Đáp án:** List.of không cho phép null elements và ném NullPointerException ngay khi tạo list.

**Bài 3.** Null row khác null field thế nào?  
**Đáp án:** Null row là phần tử không tồn tại; null field là record có tồn tại nhưng thiếu một giá trị.

**Bài 4.** Vì sao nên có RejectReason enum?  
**Đáp án:** Reason code ổn định giúp thống kê, test và xử lý upstream mà không phải parse exception messages.

**Bài 5.** Nếu ID được strip, " A " và "A" có duplicate không?  
**Đáp án:** Có trong policy demo, vì cả hai normalize thành A.

**Bài 6.** "A" và "a" có duplicate trong demo không?  
**Đáp án:** Không; policy phân biệt hoa/thường.

**Bài 7.** Một record ID=X nhưng value null xuất hiện trước record ID=X value=10. Record nào được nhận?  
**Đáp án:** Record thứ hai, vì validation xảy ra trước dedupe và invalid record không chiếm ID.

**Bài 8.** first-valid-wins có phụ thuộc thứ tự input không?  
**Đáp án:** Có. Nếu đổi thứ tự các duplicate hợp lệ, record thắng có thể đổi.

**Bài 9.** HashSet có giữ thứ tự input không?  
**Đáp án:** Không có order contract; demo chỉ dùng Set để lookup và giữ output trong ArrayList.

**Bài 10.** Vì sao enhanced-for tốt hơn indexed get trên LinkedList?  
**Đáp án:** Iterator duyệt tuyến tính; gọi get(index) liên tục có thể tạo O(n²).

**Bài 11.** Primitive long overflow có tự ném exception không?  
**Đáp án:** Không; có thể wrap around. Dùng Math.addExact hoặc BigInteger.

**Bài 12.** Khi nào BigInteger phù hợp cho aggregate?  
**Đáp án:** Khi tổng có thể vượt miền long nhưng vẫn cần kết quả chính xác.

**Bài 13.** Vì sao BigDecimal("10.20").equals(BigDecimal("10.2")) là false?  
**Đáp án:** equals xét cả scale; compareTo so sánh giá trị số học.

**Bài 14.** Min/max của empty result nên là gì?  
**Đáp án:** OptionalLong.empty, vì không có giá trị min/max thực.

**Bài 15.** Có nên thay null amount bằng 0 mặc định?  
**Đáp án:** Chỉ khi business contract định nghĩa null tương đương 0; nếu không sẽ che thiếu dữ liệu.

**Bài 16.** Dedupe theo toàn bộ record có luôn đúng không?  
**Đáp án:** Không. Phải dùng business key phù hợp với identity của dữ liệu.

**Bài 17.** ParallelStream với HashSet mutable có an toàn không?  
**Đáp án:** Không. HashSet không thread-safe; concurrent set cũng chưa đảm bảo first-wins deterministic.

**Bài 18.** Dedupe trong một batch có đảm bảo dedupe giữa nhiều batch không?  
**Đáp án:** Không. Cần persistent state/unique constraint/idempotency key hoặc window policy.

**Bài 19.** Thêm null row vào cuối input nên ảnh hưởng thế nào trong demo?  
**Đáp án:** Accepted không đổi, rejected tăng một với reason NULL_RECORD.

**Bài 20.** Vì sao cần kiểm tra output immutability?  
**Đáp án:** Để caller không thể sửa kết quả đã được tính và làm sai invariant downstream.

**Bài 21.** Có nên catch mọi RuntimeException rồi biến thành rejected row?  
**Đáp án:** Không. Có thể che lỗi lập trình hoặc lỗi hệ thống; chỉ phân loại lỗi record-level đã định nghĩa.

**Bài 22.** Benchmark pipeline nên dùng dữ liệu nào?  
**Đáp án:** Dataset đại diện về kích thước, tỷ lệ null/duplicate, key distribution, độ dài chuỗi và boundary values.

**Bài 23.** Chunking có tự giải quyết global duplicate không?  
**Đáp án:** Không. Nếu reset seen set theo chunk, duplicate giữa các chunk vẫn lọt.

**Bài 24.** Nếu input order không ổn định, first-wins có phù hợp không?  
**Đáp án:** Chưa chắc. Cần sequence/version hoặc tie-breaker deterministic theo business.

## 17. Checklist production

- [ ] Xác định null source là exception hay empty theo contract.
- [ ] Xác định empty source trả kết quả gì.
- [ ] Phân biệt null row, null field, blank string và zero.
- [ ] Có reason code cho từng loại record bị reject.
- [ ] Quy định partial acceptance hay all-or-nothing.
- [ ] Xác định duplicate business key.
- [ ] Xác định normalization của key: whitespace, case và Unicode.
- [ ] Ghi rõ first-wins, last-wins, reject-all hoặc aggregate.
- [ ] Validation/normalization/dedup stage có thứ tự rõ ràng.
- [ ] Invalid record không chiếm key nếu policy yêu cầu như vậy.
- [ ] Giữ source index/correlation ID để truy ngược.
- [ ] Test null/empty/duplicate và boundary riêng.
- [ ] Test Long.MIN_VALUE, Long.MAX_VALUE và aggregate overflow.
- [ ] Dùng Math.addExact hoặc BigInteger theo contract.
- [ ] Với decimal, xác định precision, scale và rounding.
- [ ] Với time, xác định timezone, precision và boundary transitions.
- [ ] Giữ output order deterministic nếu downstream cần.
- [ ] Trả immutable result hoặc ownership contract rõ.
- [ ] Đảm bảo accepted + rejected accounting khớp input.
- [ ] Không dùng null-to-default để che thiếu dữ liệu.
- [ ] Không dùng parallel dedupe nếu chưa thiết kế deterministic partition/merge.
- [ ] Xác định duplicate scope trong một batch, nhiều batch hay toàn hệ thống.
- [ ] Có idempotency strategy cho side effects và retry.
- [ ] Với nguồn lớn, dùng bounded batches/backpressure và giữ dedupe state đúng scope.
- [ ] Benchmark bằng dữ liệu thực tế; dùng JMH/profiler khi cần.
- [ ] Đo throughput, tail latency, allocation, GC và reject rates.
- [ ] Chạy lại correctness suite sau mọi tối ưu.

## 18. Tài liệu chính thức và nguồn tham khảo hiện hành

1. [Oracle Java SE 26 — List: size, iteration, immutable factory/copy APIs](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html)
2. [Oracle Java SE 26 — String: isBlank, strip và Unicode whitespace](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/String.html)
3. [Oracle Java SE 26 — Objects: requireNonNull và null checks](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Objects.html)
4. [Oracle Java SE 26 — HashSet: uniqueness and hash-based lookup](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/HashSet.html)
5. [Oracle Java SE 26 — BigInteger: arbitrary-precision integer arithmetic](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigInteger.html)
6. [Oracle Java SE 26 — BigDecimal: decimal arithmetic, scale and comparison](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigDecimal.html)
7. [Oracle Java SE 26 — Math.addExact: checked integer arithmetic](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Math.html)
8. [Oracle Java SE 26 — OptionalLong: optional primitive long result](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/OptionalLong.html)
9. [Oracle Java SE 26 — Stream: ordering, stateful operations and parallel pipelines](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html)
10. [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh)
11. [Oracle Java SE 26 — Java Flight Recorder](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/module-summary.html)

**Ghi nhớ:** Pipeline tốt phải phân biệt **nguồn null**, **nguồn rỗng**, **record null**, **field null**, **duplicate** và **giá trị ở biên**. Chọn policy rõ ràng, ghi nhận record bị reject, giữ duplicate handling deterministic và kiểm tra overflow/precision. Tối ưu bằng một lượt duyệt và cấu trúc dữ liệu phù hợp khi semantics cho phép; với dữ liệu lớn hoặc chạy phân tán, cần tính cả memory, backpressure, dedupe scope và idempotency. Hãy đo bằng dữ liệu đại diện và chạy lại toàn bộ invariant tests sau mỗi thay đổi.
