# Chọn dừng khi có lỗi hoặc thu thập lỗi cùng kết quả

## 1. Một pipeline có lỗi nên dừng ngay hay tiếp tục?

Trong module **JAVA_STREAM_API**, các pipeline `filter`, `map`, `reduce` và `collect` giúp xử lý dữ liệu khai báo qua nhiều bước lazy. Khi một phần tử đầu vào không hợp lệ, có ít nhất hai chiến lược khác nhau:

- **Fail-fast (dừng khi có lỗi):** từ chối phần tử sai và làm cả thao tác thất bại, không trả báo cáo thành công từ dữ liệu thiếu.
- **Error accumulation (thu thập lỗi cùng kết quả):** biến mỗi phần tử thành **kết quả hợp lệ hoặc lỗi có cấu trúc**, rồi gom cả giá trị thành công lẫn lỗi vào một báo cáo.

Hai chiến lược không có cái nào đúng trong mọi tình huống. Nếu làm việc với số tiền phải đối soát tuyệt đối, bỏ đi một dòng có thể khiến báo cáo sai nghiêm trọng. Nếu làm công cụ nhập 10.000 dòng để người dùng sửa nhiều lỗi một lượt, dừng ở dòng đầu tiên lại gây trải nghiệm kém.

Ví dụ tệp đơn hàng dạng CSV tối giản:

```text
1  O-101,1200,HN
2  O-102,500,HCM
3  malformed-line
4
5  O-103,-5,HN
6  O-104,700,DN
7  O-105,100,HN
```

Quy ước: mỗi dòng có ba trường `orderId,amountCents,region`; dòng trắng được đếm riêng và bỏ qua; ID có dạng `O-` theo sau ba chữ số; số tiền không âm; mã vùng có 2–3 chữ cái in hoa.

Đối với dữ liệu này:

| Thống kê | Giá trị |
| --- | ---: |
| Tổng dòng vật lý | 7 |
| Dòng hợp lệ | 4 |
| Dòng trắng | 1 |
| Dòng sai định dạng/giá trị | 2 |
| Tổng tiền của bốn đơn hợp lệ | 2.500 cents |
| Dòng lỗi đầu tiên | 3 — thiếu trường |
| Dòng lỗi còn lại | 5 — số tiền âm |

Nếu chọn fail-fast, kết quả là một **lỗi tại dòng 3**, không có `BatchReport` thành công. Nếu chọn thu thập lỗi, kết quả có thể gồm bốn `Order` hợp lệ, hai `RowIssue` và các bộ đếm. Tuy nhiên, **báo cáo thành công về kỹ thuật không tự có nghĩa được phép xuất bản hoặc ghi dữ liệu nghiệp vụ**.

### Mục tiêu học tập

Sau bài thuộc chương **Ngoại lệ và tính an toàn**, bạn sẽ:

1. Phân biệt lỗi dữ liệu có thể dự đoán với lỗi I/O, lỗi lập trình và lỗi dịch vụ ngoài.
2. Chọn giữa fail-fast, collect-all, skip-with-count và chính sách kết hợp có giới hạn.
3. Viết parser thuần trả `Accepted`, `Blank` hoặc `Rejected`, không dùng `null` để che lỗi.
4. Giữ số dòng chính xác và thiết kế kiểu `BatchReport` tự kiểm chứng được.
5. Viết collector tích lũy đồng thời **giá trị đúng, bộ đếm và mẫu lỗi** mà không sửa trạng thái bên ngoài pipeline.
6. Hiểu đặc điểm của fail-fast trên stream tuần tự so với parallel và short-circuit.
7. Ngăn việc gọi dịch vụ hoặc ghi database khi chưa quyết định chấp nhận dữ liệu.
8. Kiểm thử nguồn rỗng, nhiều lỗi, giới hạn mẫu, thứ tự và các trường hợp dữ liệu biên trên Java 17.

## 2. Hợp đồng phân loại lỗi phải có trước code

Một pipeline xử lý dữ liệu không thể chỉ nói “nếu lỗi thì bỏ qua”. Phải định nghĩa **loại lỗi**, **mức độ nghiêm trọng**, **quyền tiếp tục** và **sản phẩm đầu ra**.

### 2.1. Phân loại theo nguồn gốc

| Loại | Ví dụ | Có nên xử lý như dòng sai thông thường? |
| --- | --- | --- |
| **Lỗi schema** | Thiếu cột, mã vùng sai, số tiền âm | Có, nếu policy cho phép |
| **Dòng trắng hợp lệ theo đặc tả** | Dòng trống xen giữa các bản ghi | Không phải lỗi; đếm riêng |
| **Lỗi quy tắc liên bản ghi** | Hai đơn cùng ID, tổng vượt ngưỡng | Cần validation ở cấp batch, không đủ parser từng dòng |
| **Lỗi I/O** | Không mở được file, mất kết nối khi đọc | **Không** lặng lẽ chuyển thành dòng sai |
| **Lỗi lập trình** | `NullPointerException` do bug, sai invariant | Không bắt chung rồi coi là dữ liệu thiếu |
| **Lỗi dịch vụ ngoài** | Timeout khi ghi đơn, database từ chối | Không nằm trong `ParseOutcome`; cần workflow/result riêng |
| **Lỗi tài nguyên** | Hết bộ nhớ, hủy tác vụ | Không nên bỏ qua để báo thành công |

Việc bắt `RuntimeException` hoặc `Exception` ở mọi chỗ rồi chuyển sang một trạng thái `INVALID_ROW` rất nguy hiểm: lỗi lập trình có thể bị ẩn thành “có vài dòng sai”.

### 2.2. Ba trạng thái mỗi dòng

```text
                  Dòng vật lý số N
                         │
                         ▼
                  parse(N, raw)
                         │
              ┌──────────┼───────────┐
              ▼          ▼           ▼
           Accepted     Blank       Rejected
           Order        number      RowIssue
              │          │           │
          valid++      blank++     invalid++
          giữ Order                  policy?
```

Với một lượt đọc đã hoàn tất bình thường, bất biến:

\[
\text{totalLines}=\text{validLines}+\text{blankLines}+\text{invalidLines}.
\]

Đây là một phép kiểm tra mạnh hơn việc chỉ đối chiếu `orders.size()`: nó ngăn các dòng sai âm thầm biến mất qua `filter`.

### 2.3. Dòng sai có thể có nhiều nguyên nhân

Một dòng như `O-ABC,-2,?` có nhiều lỗi. Có hai chính sách:

- **Một lỗi đầu tiên trên mỗi dòng:** parser kiểm tra theo thứ tự và trả mã lỗi đầu tiên. Bài này dùng cách đó; dễ dự đoán và tối ưu.
- **Mọi lỗi trường trong một dòng:** parser tích lũy `List<FieldIssue>` cho một dòng rồi trả `Rejected` gồm nhiều chi tiết; phù hợp với giao diện chỉnh sửa biểu mẫu.

Đừng ngầm gọi một parser “thu thập tất cả lỗi” nếu mỗi dòng chỉ giữ **lỗi đầu tiên**. Bài sẽ thu thập nhiều **dòng lỗi** trên toàn bộ dữ liệu, không cam kết gom toàn bộ lỗi của mọi trường trong một dòng.

## 3. Ma trận chọn chính sách dừng hoặc tiếp tục

| Chính sách | Khi phát hiện dòng sai | Kết quả cuối nếu có lỗi dữ liệu | Phù hợp khi |
| --- | --- | --- | --- |
| **FAIL_FAST** | Ném lỗi, dừng pipeline tuần tự ở vị trí lỗi đầu tiên được gặp | Không trả kết quả thành công | Kiểm soát dữ liệu nghiêm ngặt |
| **COLLECT_ALL** | Ghi một issue cho mỗi dòng sai, tiếp tục | Report chứa cả bản ghi hợp lệ lẫn mọi issue | Công cụ nhập dữ liệu nhỏ/vừa, cần sửa nhiều lỗi |
| **SKIP_WITH_COUNT** | Tăng bộ đếm, không giữ chi tiết | Report có `invalidLines` nhưng `issues` rỗng | Telemetry best effort, lưu tối thiểu |
| **COLLECT_BOUNDED** | Tăng bộ đếm và giữ tối đa `k` mẫu lỗi | Report có đủ tổng lỗi và tối đa `k` issue | Tệp lớn, muốn khống chế RAM |
| **THRESHOLD** | Thu lỗi, sau đó áp dụng ngưỡng cho phép | Report kỹ thuật có thể bị đánh dấu “không xuất bản” | Nhập dữ liệu theo SLA/quality gate |

Các lựa chọn **không thay thế chính sách lỗi I/O**: trong mọi chế độ, không thể đọc tệp thì không được tự diễn giải thành “nguồn rỗng”. Một báo cáo từng phần do lỗi đọc phải có loại kết quả riêng và số byte/dòng đã đọc được ghi rõ.

### 3.1. Quy tắc lựa chọn nhanh

Hãy hỏi:

1. **Một dòng bị bỏ có làm sai nghĩa nghiệp vụ không?** Nếu có, ưu tiên fail-fast hoặc thu thập rồi **chặn bước ghi**.
2. **Người dùng cần xem nhiều lỗi một lần không?** Nếu có, thu thập lỗi.
3. **Tệp có thể rất lớn không?** Nếu có, dùng bộ đếm đầy đủ và mẫu lỗi có giới hạn, hoặc xuất lỗi theo luồng ra kho riêng có kiểm soát.
4. **Có đang gọi thanh toán/gửi email/ghi DB không?** Nếu có, không thực hiện side effect trong mapper trước khi quality gate hoàn tất.
5. **Chính sách cần “mọi lỗi” hay “một số ví dụ lỗi”?** Nếu chỉ lấy mẫu, phải ghi nhãn chính xác.

### 3.2. Tạm dừng việc xuất bản khác với dừng parsing

Một công cụ import có thể **đọc hết file** để trả tất cả lỗi, nhưng **không ghi một đơn nào** khi `invalidLines > 0`. Đây là chính sách *validate all, commit none*:

```text
Tệp → Parse toàn bộ → BatchReport
                         │
                    invalidLines > 0 ?
                      /          \
                    Có           Không
                    │              │
             Trả lỗi để sửa    Cho phép ghi
             (không ghi DB)        DB
```

Điều này khác với “bỏ dòng sai, ghi những dòng đúng”. Cả hai có thể triển khai trên cùng `BatchReport`, nhưng quyết định **commit** phải là một bước nghiệp vụ tường minh.

## 4. Vì sao `filter(Objects::nonNull)` không phải xử lý lỗi?

Phản mẫu:

```java
List<Order> valid = rawLines.stream()
    .map(line -> parseOrNull(line))
    .filter(java.util.Objects::nonNull)
    .toList();
```

Nếu `parseOrNull` trả null cho dòng sai, kết quả chỉ gồm các bản ghi còn sót lại. Nó không trả:

- Số lượng dòng bị bỏ.
- Vị trí vật lý của dòng sai.
- Loại lỗi.
- Có phải source I/O lỗi trước khi đọc hết không.
- Dữ liệu này có được phép ghi hay chỉ được xem trước.

**`Optional<Order>` cũng chưa đủ** nếu miền nghiệp vụ cần phân biệt dòng trắng, sai schema và lỗi tạm thời. `Optional.empty()` chỉ diễn đạt “không có giá trị”; dùng kiểu có trạng thái rõ ràng sẽ giữ thông tin cần kiểm toán.

```java
sealed interface ParseOutcome
    permits Accepted, Blank, Rejected {}

record Accepted(long lineNumber, Order value)
    implements ParseOutcome {}

record Blank(long lineNumber) implements ParseOutcome {}

record Rejected(RowIssue issue) implements ParseOutcome {}
```

Ở đây, các record là immutable ở mức thành phần đã chọn: `Order` nên là value object bất biến; `RowIssue` có số dòng và mã lỗi. Không cần trả toàn bộ raw line nếu dòng có thể chứa token hoặc dữ liệu nhạy cảm.

## 5. Chọn fail-fast khi cần dữ liệu đầy đủ và hợp lệ

Một parser thuần có thể trả `Rejected`; hàm fail-fast chuyển trường hợp này thành **ngoại lệ domain**:

```java
List<Order> accepted = java.util.stream.IntStream
    .range(0, lines.size())
    .mapToObj(i -> parse(i + 1L, lines.get(i)))
    .map(outcome -> {
        if (outcome instanceof Rejected bad) {
            throw new InvalidRowException(bad.issue());
        }
        return outcome;
    })
    .filter(Accepted.class::isInstance)
    .map(Accepted.class::cast)
    .map(Accepted::value)
    .toList();
```

Đoạn minh họa dùng `parse`, `lines` và các kiểu `ParseOutcome` sẽ được định nghĩa trong chương trình hoàn chỉnh ở mục 9.

Với một **stream tuần tự có encounter order**, phép đánh giá này dừng khi gặp `Rejected` đầu tiên trong thứ tự duyệt: ví dụ là **dòng 3**. Không có danh sách `accepted` được trả thành công; các giá trị trước lỗi chỉ nằm trong trạng thái nội bộ của pipeline.

### 5.1. “Fail-fast” không phải rollback

Nếu đặt một lệnh ghi trong mapper trước `Rejected`:

```java
// SAI với yêu cầu all-or-nothing:
// lines.stream()
//     .map(parseAndSaveToDatabase)
//     .toList();
```

thì ngoại lệ ở dòng 3 **không tự hoàn tác** những dòng 1 và 2 đã ghi. Fail-fast chỉ mô tả **dừng đánh giá khi thấy lỗi**, không mô tả giao dịch giữa các hệ thống.

### 5.2. Với parallel stream, “lỗi đầu tiên” không hẳn là dòng nhỏ nhất

`parallel()` có thể đánh giá các phân đoạn khác nhau đồng thời. Một lỗi ở dòng 50 có thể được quan sát trước lỗi ở dòng 3; công việc ở những phân đoạn khác có thể đã bắt đầu trước khi pipeline ngừng.

Nếu thông điệp lỗi **phải là lỗi ở số dòng nhỏ nhất**, các lựa chọn rõ ràng hơn là:

- Dùng pipeline **tuần tự** với nguồn có encounter order.
- Hoặc thu thập các lỗi rồi **sắp theo số dòng** và lấy lỗi đầu tiên về mặt dữ liệu.

Không dùng `parallelStream().findAny()` để khẳng định đã tìm “dòng lỗi đầu tiên” trong file.

### 5.3. Một lỗi parser thuần là khác lỗi đọc nguồn

`InvalidRowException` nói **dòng đã đọc được** không hợp lệ. `IOException` khi mở file và `UncheckedIOException` khi duyệt file phải giữ ý nghĩa riêng. Nếu reader chỉ đọc được hai dòng rồi lỗi I/O, không thể trả `BatchReport(totalLines=2, invalidLines=0)` và nói rằng file hoàn toàn hợp lệ.

## 6. Thu thập lỗi cùng kết quả: không đánh mất dòng nào

Thay vì ném khi thấy `Rejected`, có thể gom mọi `ParseOutcome` thành **hai luồng dữ liệu logic**: giá trị hợp lệ và issue.

```text
List<String> đã đọc đủ
          │
      stream/index
          │
       parse()
          │
    ┌─────┴───────────────────────┐
    ▼                             ▼
 Accepted                     Blank / Rejected
    │                             │
 List<Order>                 blankCount / invalidCount
                                  │
                         List<RowIssue> (có giới hạn)
    └──────────┬──────────────────┘
               ▼
           BatchReport
```

Kết quả chứa **đủ bản ghi hợp lệ** và thông tin những gì không thể chuyển thành `Order`:

```java
record BatchReport(
    long totalLines,
    long validLines,
    long blankLines,
    long invalidLines,
    List<Order> orders,
    List<RowIssue> issueSamples
) {}
```

Lưu ý: `issueSamples` chỉ giữ tối đa `sampleLimit` lỗi. Nếu yêu cầu thật sự là **mọi lỗi**, đặt giới hạn đủ lớn hoặc thiết kế kho lỗi riêng; không gọi một danh sách bị cắt là “tất cả lỗi”.

### 6.1. Bất biến quan trọng của báo cáo

Nếu toàn bộ input được đọc và không có ngoại lệ ngoài dự kiến:

\[
\begin{aligned}
  \text{totalLines} &= \text{validLines}+\text{blankLines}+\text{invalidLines},\\
  |\text{orders}| &= \text{validLines},\\
  |\text{issueSamples}| &\leq \min(\text{invalidLines},\text{sampleLimit}).
\end{aligned}
\]

Khi `sampleLimit = 0`, chỉ có bộ đếm, không lưu chi tiết lỗi. Khi `sampleLimit` lớn hơn hoặc bằng tổng lỗi, danh sách chứa tất cả issue theo chính sách một issue/dòng của parser.

### 6.2. Số dòng phải được tạo từ nguồn, không từ side effect trong mapper

Khi nguồn là `List<String>`, dùng:

```java
java.util.stream.IntStream.range(0, lines.size())
    .mapToObj(i -> parse(i + 1L, lines.get(i)));
```

Số dòng được suy từ **chỉ số nguồn**, không phụ thuộc thứ tự thực thi lambda. Tránh:

```java
// Dễ sai với parallel stream và ngữ nghĩa điều khiển:
// AtomicLong counter = new AtomicLong();
// lines.parallelStream()
//     .map(line -> parse(counter.incrementAndGet(), line));
```

`AtomicLong` bảo đảm phép tăng atomic nhưng **không gắn số dòng đúng với vị trí nguồn** khi nhiều thread xử lý không theo thứ tự. Với nguồn I/O đọc lười, cần một source/iterator đánh số dòng theo thứ tự hoặc một `Spliterator` được thiết kế phù hợp; không đưa trách nhiệm đó vào mapper có shared mutable state.

## 7. Thu hai loại kết quả trong một lượt: collector tùy chỉnh

Một cách ngây thơ là làm hai lần:

```java
// parse bị chạy hai lần, và không thể dùng lại stream đã tiêu thụ:
// var valid = outcomes.stream().filter(...).toList();
// var invalid = outcomes.stream().filter(...).toList();
```

Nếu `outcomes` là `List` đã materialize, hai lượt có thể chấp nhận được. Nhưng nếu nguồn là stream I/O chỉ duyệt một lần, hoặc parser đắt đỏ, **một collector** gom cả giá trị và lỗi sẽ rõ ràng hơn.

Một `Collector<ParseOutcome, Accumulator, BatchReport>` có bốn phần:

| Phần | Vai trò |
| --- | --- |
| `supplier` | Tạo `Accumulator` riêng cho một phân vùng |
| `accumulator` | Nhận từng `Accepted`/`Blank`/`Rejected` và cập nhật counters/lists |
| `combiner` | Gộp hai accumulator khi pipeline cần |
| `finisher` | Trả `BatchReport` với collection snapshot |

Code minh họa:

```java
.collect(java.util.stream.Collector.of(
    () -> new Accumulator(sampleLimit),
    Accumulator::add,
    Accumulator::combine,
    Accumulator::finish
));
```

Trạng thái mutable **nằm trong collector**, không nằm ở biến static hoặc `ArrayList` bên ngoài pipeline. Collector **không khai `CONCURRENT`**, nên framework phải bảo vệ ownership của từng container khi đánh giá song song.

### 7.1. Combiner và thứ tự mẫu lỗi

Nếu muốn lưu **N issue đầu theo encounter order** từ một ordered stream, combiner phải:

1. Giữ phần kết quả bên trái trước phần bên phải.
2. Nối các issue bên phải khi danh sách chưa đạt giới hạn.
3. Không tự sắp theo thời điểm thread hoàn tất.

Với `sampleLimit = 2`, đoạn trái có lỗi dòng 3, đoạn phải có lỗi dòng 5 và 9: khi gộp kết quả theo encounter order, chỉ giữ **3 và 5**. Cách lấy giới hạn đầu mỗi đoạn rồi nối có thể dùng để tạo đúng giới hạn đầu toàn tập nếu combiner tuân thứ tự và tính kết hợp.

### 7.2. Khi nào không nên dùng collector giữ mọi kết quả?

Nếu có hàng triệu dòng hợp lệ, `List<Order>` sẽ dùng bộ nhớ tỷ lệ với số phần tử. Dù danh sách lỗi được giới hạn, báo cáo vẫn có thể quá lớn. Khi đó:

- Thu **counters + aggregate** mà không giữ toàn bộ `Order` nếu chỉ cần thống kê.
- Hoặc xử lý theo chunk, ghi staging và kiểm soát checkpoint.
- Nếu bắt buộc xem mọi lỗi, streaming chúng vào một kho lỗi có retention/kiểm soát truy cập, thay vì dồn toàn bộ vào RAM.

Không vì muốn pipeline trông ngắn mà âm thầm tạo một `List` vượt giới hạn bộ nhớ có thể có.

## 8. Thiết kế API cho báo cáo có lỗi

Ví dụ đầy đủ sẽ công khai hai phương thức:

```java
static List<Order> validateFailFast(List<String> lines);

static BatchReport collectIssues(
    List<String> lines,
    int sampleLimit
);
```

**`validateFailFast`** chỉ trả danh sách bản ghi đã được validate nếu toàn bộ nguồn đáp ứng chính sách. Khi gặp `Rejected`, nó ném `InvalidRowException` mang `RowIssue`. Dòng trắng được quy định là hợp lệ nhưng **không tạo Order**.

**`collectIssues`** không ném vì **lỗi dữ liệu được dự kiến**. Nó vẫn có thể ném vì lỗi lập trình/đầu vào không hợp lệ (ví dụ `lines == null`), hoặc vì overflow được kiểm tra bằng `Math.addExact`. Nó trả:

```text
BatchReport
  totalLines:    7
  validLines:    4
  blankLines:    1
  invalidLines:  2
  orders:        [O-101, O-102, O-104, O-105]
  issueSamples:  [line 3 FIELD_COUNT, line 5 NEGATIVE_AMOUNT]
```

Ở đây, `issueSamples` không phải audit đầy đủ khi `sampleLimit` thấp hơn tổng lỗi. **Bộ đếm `invalidLines` mới là số dòng lỗi**, còn danh sách issue là phần chẩn đoán.

### 8.1. Không trả object chưa hoàn chỉnh khi fail-fast

Một số code tạo `List<Order> values` bên ngoài stream rồi `map`/`forEach` thêm từng phần tử vào đó, sau đó gặp lỗi:

```java
// Phản mẫu: caller có thể thấy một List chỉ có tiền tố các dòng hợp lệ.
// List<Order> values = new ArrayList<>();
// lines.stream().map(OrderBatchValidation::parse)
//     .forEach(o -> values.add(...));
```

Trong phương thức fail-fast của bài, các kết quả trung gian là **nội bộ** và không được công bố nếu có exception. Điều đó tránh trả một danh sách không đầy đủ với tên gọi “valid orders”.

### 8.2. Không dùng report kỹ thuật để ngầm cho phép ghi

Một `BatchReport` có thể chứa dữ liệu hợp lệ ngay cả khi `invalidLines > 0`, nhưng caller phải quyết định:

```java
BatchReport report = collectIssues(lines, 20);

if (report.invalidLines() != 0L) {
    // Trả báo cáo validation cho người dùng; chưa ghi database.
} else {
    // Đã qua bước validation theo dòng; còn có thể cần kiểm tra
    // trùng ID, chính sách hạn mức, authorization và transaction.
}
```

## 9. Chương trình Java 17 hoàn chỉnh: `OrderBatchValidation`

Đoạn code sau có thể lưu thành `OrderBatchValidation.java` và chạy độc lập bằng Java 17+. Nó không phụ thuộc cơ sở dữ liệu, framework hoặc dịch vụ ngoài.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collector;
import java.util.stream.IntStream;

public final class OrderBatchValidation {

    private OrderBatchValidation() {}

    public enum ErrorCode {
        FIELD_COUNT,
        INVALID_ID,
        INVALID_AMOUNT,
        NEGATIVE_AMOUNT,
        INVALID_REGION
    }

    public record Order(
        String id,
        long amountCents,
        String region
    ) {
        public Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(region, "region");
            if (!id.matches("O-[0-9]{3}")) {
                throw new IllegalArgumentException("ID không hợp lệ");
            }
            if (amountCents < 0L) {
                throw new IllegalArgumentException("Số tiền âm");
            }
            if (!region.matches("[A-Z]{2,3}")) {
                throw new IllegalArgumentException("Mã vùng không hợp lệ");
            }
        }
    }

    public record RowIssue(long lineNumber, ErrorCode code) {
        public RowIssue {
            if (lineNumber < 1L) {
                throw new IllegalArgumentException("lineNumber phải >= 1");
            }
            Objects.requireNonNull(code, "code");
        }
    }

    public sealed interface ParseOutcome
        permits Accepted, Blank, Rejected {}

    public record Accepted(long lineNumber, Order order)
        implements ParseOutcome {}

    public record Blank(long lineNumber)
        implements ParseOutcome {}

    public record Rejected(RowIssue issue)
        implements ParseOutcome {}

    public static final class InvalidRowException
            extends RuntimeException {
        private final RowIssue issue;

        public InvalidRowException(RowIssue issue) {
            super("Dòng " + issue.lineNumber() +
                  " không hợp lệ: " + issue.code());
            this.issue = issue;
        }

        public RowIssue issue() {
            return issue;
        }
    }

    public record BatchReport(
        long totalLines,
        long validLines,
        long blankLines,
        long invalidLines,
        List<Order> orders,
        List<RowIssue> issueSamples
    ) {
        public BatchReport {
            // Chụp riêng cấu trúc collection để không lộ state collector.
            orders = List.copyOf(orders);
            issueSamples = List.copyOf(issueSamples);
        }

        public boolean hasDataErrors() {
            return invalidLines > 0L;
        }

        public long acceptedTotalCents() {
            return orders.stream()
                .mapToLong(Order::amountCents)
                .reduce(0L, Math::addExact);
        }
    }

    // Hàm thuần: cùng (lineNumber, raw) cho cùng outcome hoặc lỗi input.
    public static ParseOutcome parse(long lineNumber, String raw) {
        if (lineNumber < 1L) {
            throw new IllegalArgumentException(
                "lineNumber phải >= 1"
            );
        }
        Objects.requireNonNull(raw, "raw");

        if (raw.isBlank()) {
            return new Blank(lineNumber);
        }

        // -1 giữ trường rỗng cuối, tránh bỏ sót lỗi thiếu giá trị.
        String[] fields = raw.split(",", -1);
        if (fields.length != 3) {
            return new Rejected(
                new RowIssue(lineNumber, ErrorCode.FIELD_COUNT)
            );
        }

        String id = fields[0].strip();
        String amountText = fields[1].strip();
        String region = fields[2].strip();

        if (!id.matches("O-[0-9]{3}")) {
            return new Rejected(
                new RowIssue(lineNumber, ErrorCode.INVALID_ID)
            );
        }

        long amount;
        try {
            amount = Long.parseLong(amountText);
        } catch (NumberFormatException ex) {
            return new Rejected(
                new RowIssue(lineNumber, ErrorCode.INVALID_AMOUNT)
            );
        }

        if (amount < 0L) {
            return new Rejected(
                new RowIssue(lineNumber, ErrorCode.NEGATIVE_AMOUNT)
            );
        }

        if (!region.matches("[A-Z]{2,3}")) {
            return new Rejected(
                new RowIssue(lineNumber, ErrorCode.INVALID_REGION)
            );
        }

        return new Accepted(
            lineNumber,
            new Order(id, amount, region)
        );
    }

    // FAIL_FAST: chỉ dùng stream tuần tự để báo lỗi theo thứ tự dòng.
    public static List<Order> validateFailFast(List<String> lines) {
        Objects.requireNonNull(lines, "lines");

        return IntStream.range(0, lines.size())
            .mapToObj(i -> parse(i + 1L, lines.get(i)))
            .map(outcome -> {
                if (outcome instanceof Rejected rejected) {
                    throw new InvalidRowException(rejected.issue());
                }
                return outcome;
            })
            .filter(Accepted.class::isInstance)
            .map(Accepted.class::cast)
            .map(Accepted::order)
            .toList();
    }

    private static final class Accumulator {
        final int sampleLimit;
        long totalLines;
        long validLines;
        long blankLines;
        long invalidLines;
        final List<Order> orders = new ArrayList<>();
        final List<RowIssue> issues = new ArrayList<>();

        Accumulator(int sampleLimit) {
            this.sampleLimit = sampleLimit;
        }

        void add(ParseOutcome outcome) {
            totalLines = Math.addExact(totalLines, 1L);

            if (outcome instanceof Accepted accepted) {
                validLines = Math.addExact(validLines, 1L);
                orders.add(accepted.order());
            } else if (outcome instanceof Blank) {
                blankLines = Math.addExact(blankLines, 1L);
            } else if (outcome instanceof Rejected rejected) {
                invalidLines = Math.addExact(invalidLines, 1L);
                if (issues.size() < sampleLimit) {
                    issues.add(rejected.issue());
                }
            } else {
                throw new IllegalStateException("Unknown outcome");
            }
        }

        Accumulator combine(Accumulator right) {
            totalLines = Math.addExact(totalLines, right.totalLines);
            validLines = Math.addExact(validLines, right.validLines);
            blankLines = Math.addExact(blankLines, right.blankLines);
            invalidLines = Math.addExact(invalidLines, right.invalidLines);

            // Với ordered source, nối các phần theo encounter order.
            orders.addAll(right.orders);
            for (RowIssue issue : right.issues) {
                if (issues.size() >= sampleLimit) {
                    break;
                }
                issues.add(issue);
            }
            return this;
        }

        BatchReport finish() {
            return new BatchReport(
                totalLines,
                validLines,
                blankLines,
                invalidLines,
                orders,
                issues
            );
        }
    }

    // COLLECT_BOUNDED: bộ đếm đầy đủ, số issue lưu có giới hạn.
    public static BatchReport collectIssues(
        List<String> lines,
        int sampleLimit
    ) {
        Objects.requireNonNull(lines, "lines");
        if (sampleLimit < 0) {
            throw new IllegalArgumentException(
                "sampleLimit phải >= 0"
            );
        }

        return IntStream.range(0, lines.size())
            .mapToObj(i -> parse(i + 1L, lines.get(i)))
            .collect(Collector.of(
                () -> new Accumulator(sampleLimit),
                Accumulator::add,
                Accumulator::combine,
                Accumulator::finish
            ));
    }

    public static List<String> sample() {
        return List.of(
            "O-101,1200,HN",
            "O-102,500,HCM",
            "malformed-line",
            "",
            "O-103,-5,HN",
            "O-104,700,DN",
            "O-105,100,HN"
        );
    }

    public static void main(String[] args) {
        List<String> input = sample();

        try {
            validateFailFast(input);
        } catch (InvalidRowException ex) {
            System.out.println(ex.getMessage());
            // Dòng 3 không hợp lệ: FIELD_COUNT
        }

        BatchReport report = collectIssues(input, 2);
        System.out.println(report.totalLines());       // 7
        System.out.println(report.validLines());       // 4
        System.out.println(report.blankLines());       // 1
        System.out.println(report.invalidLines());     // 2
        System.out.println(report.acceptedTotalCents());// 2500
        System.out.println(report.issueSamples());
        // [RowIssue[lineNumber=3, code=FIELD_COUNT],
        //  RowIssue[lineNumber=5, code=NEGATIVE_AMOUNT]]
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 OrderBatchValidation.java
java OrderBatchValidation
```

### 9.1. Phân tách trách nhiệm của các thành phần

| Thành phần | Nhiệm vụ | Có side effect nghiệp vụ? |
| --- | --- | --- |
| `parse` | Kiểm tra một dòng và trả kiểu outcome | Không |
| `validateFailFast` | Tạo đơn hợp lệ hoặc ném lỗi đầu tiên | Không |
| `Accumulator.add` | Đếm loại outcome và lưu dữ liệu nội bộ | Không, chỉ sửa state nội bộ |
| `Accumulator.combine` | Gộp hai state theo hợp đồng collector | Không, chỉ sửa state nội bộ |
| `Accumulator.finish` | Tạo report không cho sửa collection | Không |
| `BatchReport.acceptedTotalCents` | Tính tổng từ các Order đã parse | Không, có thể ném nếu overflow |
| `main` | In kết quả minh họa | Có ghi console, không có giao dịch ngoài |

**Lưu ý số học:** `long` có giới hạn. `Math.addExact` giúp phép cộng tổng tiền và các bộ đếm không âm thất bại rõ ràng nếu vượt miền giá trị. Nếu nghiệp vụ cho phép tổng vượt `Long.MAX_VALUE`, nên dùng `BigInteger`, không tự chuyển tràn số thành một issue dòng sai.

### 9.2. Tại sao `List.copyOf` nằm trong record `BatchReport`?

`Accumulator` giữ các `ArrayList` mutable để thêm dữ liệu khi collect. Nếu trả thẳng những list ấy, caller có thể sửa dữ liệu đã báo cáo. `List.copyOf` tạo **snapshot cấu trúc không sửa đổi được**.

Trong ví dụ, `Order` và `RowIssue` là record chỉ chứa chuỗi, số và enum nên không có thành phần mutable. Trong một domain khác, `List.copyOf` vẫn **không deep-copy** các phần tử mutable.

### 9.3. Lỗi input null không bị coi là dòng sai

`parse(1L, null)` ném `NullPointerException` theo chủ ý vì chữ ký `String raw` được quy định phải khác null. Điều này phân biệt:

- **Dòng text thực sự đọc được nhưng sai schema** → `Rejected`.
- **Caller truyền dữ liệu vi phạm precondition của API** → lỗi hợp đồng.

Nếu hệ thống nhận một nguồn thực sự có phần tử null hợp lệ, phải thay đổi schema/policy và test rõ ràng; không nên tự bắt `NullPointerException` rộng rồi trả `INVALID_AMOUNT`.

## 10. Phân tích sự khác biệt khi chạy chương trình

### 10.1. Với `validateFailFast(sample())`

Luồng tuần tự đánh giá các dòng theo thứ tự vật lý:

```text
Dòng 1: Accepted(O-101)
Dòng 2: Accepted(O-102)
Dòng 3: Rejected(FIELD_COUNT)
          │
          └── InvalidRowException, không trả List<Order> thành công
```

Các dòng 4–7 chưa cần parse. Nếu công việc duy nhất là validation, cách dừng sớm giúp tránh công việc thừa. Nhưng nếu mục tiêu là **trả mọi vấn đề để sửa cùng lúc**, đây không phải lựa chọn thích hợp.

### 10.2. Với `collectIssues(sample(), 2)`

Toàn bộ bảy dòng được parse:

```text
Dòng 1: Accepted → valid=1, Order O-101
Dòng 2: Accepted → valid=2, Order O-102
Dòng 3: Rejected → invalid=1, sample [FIELD_COUNT @3]
Dòng 4: Blank    → blank=1
Dòng 5: Rejected → invalid=2, sample [FIELD_COUNT @3, NEGATIVE_AMOUNT @5]
Dòng 6: Accepted → valid=3, Order O-104
Dòng 7: Accepted → valid=4, Order O-105

total=7, valid=4, blank=1, invalid=2
```

Danh sách Order giữ encounter order. `sampleLimit=2` đủ để chứa cả hai issue. Khi giảm xuống `1`, `invalidLines` **vẫn là 2** nhưng `issueSamples` chỉ còn lỗi dòng 3.

### 10.3. Với `collectIssues(sample(), 0)`

Kết quả vẫn có:

```text
validLines=4
blankLines=1
invalidLines=2
issueSamples=[]
```

Đây chính là cấu hình **SKIP_WITH_COUNT** cho lỗi dữ liệu: không lưu issue nào, nhưng không che việc có hai dòng bị loại. Còn `orders` vẫn giữ bốn bản ghi hợp lệ nên **không phải pipeline streaming với bộ nhớ O(1)**.

### 10.4. Với file hoặc danh sách rỗng

`List.<String>of()` tạo report có tất cả bộ đếm bằng 0, `orders=[]` và `issueSamples=[]`. Trong khi đó, một file không tồn tại hoặc không đọc được **không** được biến thành báo cáo rỗng: đó là lỗi của nguồn dữ liệu.

## 11. Chính sách thu lỗi không thay thế xác thực ở cấp batch

Parser từng dòng chỉ biết ba trường của **một** dòng. Nó không phát hiện được tất cả lỗi liên quan đến **nhiều bản ghi**.

### 11.1. ID trùng giữa hai dòng

Hai dòng sau đều hợp lệ riêng lẻ:

```text
O-101,1200,HN
O-101,500,HCM
```

Nhưng nếu `orderId` là khóa phải duy nhất trong batch, cần một bước kiểm tra toàn cục **sau khi** có danh sách Order hợp lệ. Có thể dùng một `Set` cục bộ trong hàm validation:

```java
static List<String> duplicateIds(List<OrderBatchValidation.Order> orders) {
    java.util.Set<String> seen = new java.util.HashSet<>();
    java.util.Set<String> duplicates = new java.util.TreeSet<>();
    for (OrderBatchValidation.Order order : orders) {
        if (!seen.add(order.id())) {
            duplicates.add(order.id());
        }
    }
    return List.copyOf(duplicates);
}
```

Đây là **một phép kiểm tra bổ sung**; nó không tự thêm lỗi duplicate vào `BatchReport.issueSamples` của ví dụ chính. Nếu muốn báo lỗi theo **vị trí dòng** chính xác ở cấp batch, cần giữ `lineNumber` cùng `Order` trong `Accepted` hoặc cấu trúc tương đương cho tới khi xác thực xong.

### 11.2. Tổng tiền, giới hạn batch và cross-field constraints

Các lỗi khác có thể chỉ lộ ra sau khi gom nhiều dòng:

- Số bản ghi vượt giới hạn được phép import.
- Một khách hàng có tổng amount vượt hạn mức.
- Hai trường hợp lệ riêng lẻ nhưng không tương thích khi kết hợp.
- Tổng tiền `long` bị tràn mặc dù từng đơn nằm trong miền số.

Không nên biến một lỗi **tổng tiền tràn** thành “dòng sai thứ N” nếu không có quy tắc xác định dòng chịu trách nhiệm. Hãy báo lỗi ở cấp **batch** hoặc thiết kế accumulator lớn như `BigInteger`.

### 11.3. Hai cấp báo cáo

Một hệ thống nghiêm túc có thể trả:

```text
ImportValidation
   ├── rowIssues: [RowIssue(...), ...]
   ├── batchIssues: [DUPLICATE_ID, TOTAL_TOO_LARGE, ...]
   ├── acceptedRows: [...]
   └── decision: ACCEPT / REJECT / PREVIEW_ONLY
```

Nhờ vậy, “dòng nào sai schema” và “batch có vi phạm quy tắc nghiệp vụ không” không bị trộn vào một exception khó giải thích.

## 12. Dừng sớm, nguồn song song và tính xác định

### 12.1. Laziness giúp dừng, nhưng không có nghĩa là đã kiểm tra hết

Trên nguồn tuần tự:

```java
boolean hasError = lines.stream()
    .map(raw -> parseOneWithoutLineNumber(raw))
    .anyMatch(outcome -> outcome instanceof Rejected);
```

Đây là **mã phác thảo** với helper `parseOneWithoutLineNumber`, không phải phương thức của lớp hoàn chỉnh ở mục 9. `anyMatch` có thể dừng ở lỗi đầu tiên đủ làm kết quả `true`. Nó trả câu trả lời “**có ít nhất một lỗi hay không**”, không trả **số lỗi**, **toàn bộ lỗi** hoặc những giá trị hợp lệ phía sau.

Nếu mục tiêu là “hiển thị mọi lỗi để sửa”, `anyMatch` không đáp ứng được dù kết quả `true` đúng.

### 12.2. Chạy song song không có nghĩa dừng tuyệt đối tại một dòng

`parallelStream` và pipeline có thể đánh giá nhiều phần tử đang chạy dở khi đã biết có lỗi. Những lời gọi intermediate operation có thể đã bắt đầu trước khi một nhánh ném exception.

Hệ quả:

- **Không đặt tác dụng phụ không đảo ngược** như thanh toán trong `map` của fail-fast pipeline.
- Không dùng bộ đếm dùng chung trong `peek` để khẳng định đã xử lý đúng N phần tử trước lỗi.
- Không phụ thuộc thứ tự ngoại lệ xuất hiện theo thời gian trên parallel stream.

Với bộ đếm và collector đúng hợp đồng, có thể tận dụng parallel stream cho các phép parse **thuần** khi có lợi ích hiệu năng. Nhưng nếu yêu cầu error samples theo **thứ tự số dòng**, cần bảo toàn encounter order hoặc sắp theo `lineNumber` ở cuối. Nếu báo cáo không đòi thứ tự, ta có thể đơn giản hơn nhưng vẫn phải bảo đảm không mất dữ liệu.

### 12.3. Tại sao collector không khai `CONCURRENT`?

Trong chương trình mẫu, `Accumulator` dùng `ArrayList` mutable. Nếu khai `CONCURRENT` sai cách, nhiều thread có thể cùng gọi `add` trên **một container**, tạo race.

Collector mặc định **không concurrent** cho phép Stream framework tạo các container cục bộ rồi kết hợp qua `combine`, kể cả khi source được đánh giá song song. Không cần ép `Collections.synchronizedList` hoặc `AtomicLong` vào mọi trường chỉ vì pipeline có `parallel()`.

### 12.4. Không hiểu nhầm “thứ tự kết quả” với “thứ tự side effect”

Một ordered stream có thể trả `List<Order>` theo encounter order, trong khi mapper của các phân vùng thực thi ở những thời điểm khác nhau. Vì vậy việc kết quả cuối giữ thứ tự **không chứng minh** những HTTP request trong mapper đã được gọi theo thứ tự đó.

Đối với nhập dữ liệu nhạy cảm, hãy parse/validate thuần trước, rồi quyết định gọi dịch vụ qua một coordinator riêng nếu cần.

## 13. Nguồn I/O: lỗi dòng dữ liệu không phải lỗi đọc tệp

`Files.lines(path, charset)` đọc lười, thích hợp cho log/CSV nhưng có vòng đời tài nguyên riêng:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static OrderBatchValidation.BatchReport analyzeSmallFile(Path file)
        throws IOException {
    List<String> lines;
    try (Stream<String> stream =
             Files.lines(file, StandardCharsets.UTF_8)) {
        lines = stream.toList();
    }
    return OrderBatchValidation.collectIssues(lines, 100);
}
```

Đoạn trên dành cho **tệp nhỏ/vừa** để dùng lại parser của bài:

1. `Files.lines` mở tài nguyên I/O.
2. `toList()` tiêu thụ stream nhưng **không tự đóng** stream.
3. `try-with-resources` đóng stream kể cả khi có exception.
4. Sau khi đã đọc hết và đóng file, `collectIssues` phân loại từng dòng trong bộ nhớ.

### 13.1. Khi file không mở được

`Files.lines` có thể ném `IOException` trong bước mở file. Đây là **lỗi nguồn**, không phải lỗi một dòng CSV. Không trả một `BatchReport` rỗng với `invalidLines=0` rồi nói file hợp lệ.

### 13.2. Khi lỗi I/O xuất hiện giữa lúc duyệt

Một lỗi đọc xảy ra **sau khi stream đã mở** có thể được bọc thành `UncheckedIOException`. Trong ví dụ, lỗi lan ra khỏi `toList()`, và `try-with-resources` vẫn thực hiện đóng nguồn.

**Không bắt toàn bộ `UncheckedIOException` để tự thêm một `RowIssue(INVALID_AMOUNT)`**; trong lỗi đọc, ta thậm chí không biết nội dung dòng chưa đọc là gì.

### 13.3. Tệp rất lớn: không materialize hết để giữ số dòng

`Files.lines(...).toList()` đưa mọi dòng vào RAM; không phù hợp với file có hàng trăm triệu bản ghi. Các lựa chọn:

- Dùng `BufferedReader.readLine()` trong một vòng lặp tuần tự có biến số dòng rõ ràng.
- Xây nguồn `Stream<NumberedLine>` từ reader/iterator, không tăng số dòng trong shared-state mapper.
- Thu **count và thống kê** mà không giữ mọi `Order`.
- Xử lý chunk với staging và checkpoint, nhưng ghi nhận ranh giới partial progress.

**Không khẳng định** rằng đưa mọi dòng vào một stream sẽ giúp pipeline tự quản lý tốc độ I/O, số lượng lỗi được giữ hay bộ nhớ. Những chính sách này phải được thiết kế.

### 13.4. Lỗi schema, lỗi encoding và dòng CSV có dấu phẩy

Parser bài này dùng `String.split(",", -1)`, **không phải parser CSV chuẩn đầy đủ**. Nếu dữ liệu có dấu phẩy trong chuỗi được quote, escape, newline trong trường hoặc dấu BOM, cần dùng grammar/parser phù hợp.

Nếu một dòng có ba trường nhưng chứa encoding sai, lỗi có thể phát sinh ở **tầng decoder**, không thể luôn quy thành `INVALID_REGION`. Hãy xác định nguồn, charset và schema trước khi chọn nơi xử lý lỗi.

## 14. Chính sách chất lượng dữ liệu sau bước thu thập

Thu thập lỗi chỉ có ích nếu caller **dùng thông tin ấy để ra quyết định**. Ví dụ:

```java
OrderBatchValidation.BatchReport report =
    OrderBatchValidation.collectIssues(lines, 20);

boolean publishable = !report.hasDataErrors();

if (!publishable) {
    // Trả report lỗi để sửa; tuyệt đối chưa gọi repository.save.
} else {
    // Tiếp tục validate cấp batch (duplicate ID, hạn mức...)
    // rồi mới cấp quyền ghi dữ liệu.
}
```

### 14.1. Ngưỡng lỗi không thay thế kiểm soát dữ liệu quan trọng

Với telemetry không yêu cầu đầy đủ tuyệt đối, có thể cho phép tối đa 0,1% dòng có nội dung bị lỗi. Tỷ lệ tính trên những dòng **không trắng**:

\[
\text{invalidRate}
= \frac{\text{invalidLines}}{\text{validLines}+\text{invalidLines}}.
\]

Nếu mẫu số bằng 0, **không tự kết luận** tỷ lệ lỗi là 0% và nguồn đủ chất lượng; đó là trường hợp **không có dữ liệu để đánh giá**.

### 14.2. Báo cáo kỹ thuật và quyết định nghiệp vụ là hai kết quả khác

Một hệ thống import có thể cần:

- `BatchReport`: số dòng, dữ liệu hợp lệ, ví dụ lỗi.
- `ValidationDecision`: được ghi, chỉ xem trước hay bị từ chối.
- `WriteReport`: đã lưu bao nhiêu, còn bao nhiêu, lỗi database/service nào.

Đừng nhét mọi loại thành công/thất bại vào một `boolean success` duy nhất. Nếu không, caller rất dễ hiểu nhầm “đã parse 90%” thành “đã nhập 100%”.

### 14.3. Giới hạn lỗi và cảnh báo phải đi đôi

Với `sampleLimit=10`, nếu `invalidLines=1000` thì danh sách lỗi chứa 10 dòng **không cho thấy 990 lỗi còn lại**. Giao diện nên hiển thị:

```text
Phát hiện 1.000 dòng không hợp lệ.
Đang hiển thị 10 lỗi đầu tiên theo thứ tự dòng.
Các lỗi còn lại không được đưa vào danh sách mẫu.
```

Nếu người dùng cần xuất **đầy đủ mọi lỗi**, cung cấp một cơ chế xuất lỗi theo luồng/kho lưu trữ có giới hạn và kiểm soát truy cập; không tự nâng `sampleLimit` lên mức không giới hạn cho file cực lớn.

## 15. Thêm kết quả từng dòng nhưng không để lộ dữ liệu nhạy cảm

`RowIssue` trong ví dụ chỉ có `lineNumber` và `ErrorCode`, đủ để biết cần mở lại vị trí nào trong nguồn. Một số công cụ nhập dữ liệu cần thêm tên trường:

```java
record FieldIssue(
    long lineNumber,
    String fieldName,
    String code
) {}
```

Ví dụ:

```text
FieldIssue(5, "amountCents", "NEGATIVE_AMOUNT")
```

Không nhất thiết phải trả nguyên văn `rawLine`, vì một dòng nguồn có thể chứa email, token, địa chỉ hoặc dữ liệu thanh toán. Nếu cho phép preview, cần:

- Giới hạn độ dài preview và loại ký tự điều khiển.
- Ẩn/sanitize dữ liệu nhạy cảm.
- Đặt retention và phân quyền truy cập hợp lý.
- Không đưa exception message từ thư viện ngoài thẳng ra API công khai nếu có nguy cơ chứa bí mật.

Một `RowIssue` có mã rõ ràng và số dòng chính xác giúp UI/CLI hiển thị thông tin đáng tin mà không phải công khai toàn bộ raw data.

## 16. Kiểm thử JUnit 5: kết quả, lỗi và chính sách giới hạn

Các test sau dùng chương trình `OrderBatchValidation` ở mục 9, chạy trên **JDK 17+** và JUnit Jupiter. Chúng xác minh **nội dung**, **số dòng**, **mã lỗi** và **quy tắc lưu lỗi mẫu**, không phụ thuộc vào thời gian của scheduler hay tên thread.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Arrays;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderBatchValidationTest {

    @Test
    void failFastStopsAtFirstInvalidLine() {
        var ex = assertThrows(
            OrderBatchValidation.InvalidRowException.class,
            () -> OrderBatchValidation.validateFailFast(
                OrderBatchValidation.sample()
            )
        );

        assertEquals(3L, ex.issue().lineNumber());
        assertEquals(
            OrderBatchValidation.ErrorCode.FIELD_COUNT,
            ex.issue().code()
        );
    }

    @Test
    void failFastAllowsBlankLinesByPolicy() {
        var orders = OrderBatchValidation.validateFailFast(
            List.of(
                "O-101,1200,HN",
                "",
                "   ",
                "O-102,500,HCM"
            )
        );

        assertEquals(2, orders.size());
        assertEquals("O-101", orders.get(0).id());
        assertEquals("O-102", orders.get(1).id());
    }

    @Test
    void accumulatesValidRowsAndAllKnownIssueCodes() {
        var report = OrderBatchValidation.collectIssues(
            OrderBatchValidation.sample(),
            10
        );

        assertEquals(7L, report.totalLines());
        assertEquals(4L, report.validLines());
        assertEquals(1L, report.blankLines());
        assertEquals(2L, report.invalidLines());
        assertEquals(4, report.orders().size());
        assertEquals(2_500L, report.acceptedTotalCents());
        assertTrue(report.hasDataErrors());

        assertEquals(
            report.totalLines(),
            report.validLines()
                + report.blankLines()
                + report.invalidLines()
        );

        assertEquals(
            new OrderBatchValidation.RowIssue(
                3L, OrderBatchValidation.ErrorCode.FIELD_COUNT
            ),
            report.issueSamples().get(0)
        );
        assertEquals(
            new OrderBatchValidation.RowIssue(
                5L, OrderBatchValidation.ErrorCode.NEGATIVE_AMOUNT
            ),
            report.issueSamples().get(1)
        );
    }

    @Test
    void limitingSamplesDoesNotLimitInvalidCount() {
        var report = OrderBatchValidation.collectIssues(
            OrderBatchValidation.sample(),
            1
        );

        assertEquals(2L, report.invalidLines());
        assertEquals(1, report.issueSamples().size());
        assertEquals(3L, report.issueSamples().get(0).lineNumber());
        assertEquals(4L, report.validLines());
    }

    @Test
    void zeroSampleLimitGivesSkipWithCount() {
        var report = OrderBatchValidation.collectIssues(
            OrderBatchValidation.sample(),
            0
        );

        assertTrue(report.issueSamples().isEmpty());
        assertEquals(2L, report.invalidLines());
        assertEquals(4, report.orders().size());
    }

    @Test
    void emptySourceHasNoRowsOrErrors() {
        var report = OrderBatchValidation.collectIssues(
            List.of(), 5
        );

        assertEquals(0L, report.totalLines());
        assertEquals(0L, report.validLines());
        assertEquals(0L, report.blankLines());
        assertEquals(0L, report.invalidLines());
        assertFalse(report.hasDataErrors());
        assertTrue(report.orders().isEmpty());
        assertTrue(report.issueSamples().isEmpty());
    }

    @Test
    void parsingDistinguishesBlankFromInvalid() {
        assertTrue(
            OrderBatchValidation.parse(1L, " \t ")
                instanceof OrderBatchValidation.Blank
        );
        assertTrue(
            OrderBatchValidation.parse(2L, "broken")
                instanceof OrderBatchValidation.Rejected
        );
        assertTrue(
            OrderBatchValidation.parse(3L, "O-101,0,HN")
                instanceof OrderBatchValidation.Accepted
        );
    }

    @Test
    void invalidAmountAndRegionGetSpecificCodes() {
        var amount = (OrderBatchValidation.Rejected)
            OrderBatchValidation.parse(1L, "O-101,abc,HN");
        var region = (OrderBatchValidation.Rejected)
            OrderBatchValidation.parse(2L, "O-101,100,?");
        var negative = (OrderBatchValidation.Rejected)
            OrderBatchValidation.parse(3L, "O-101,-1,HN");

        assertEquals(
            OrderBatchValidation.ErrorCode.INVALID_AMOUNT,
            amount.issue().code()
        );
        assertEquals(
            OrderBatchValidation.ErrorCode.INVALID_REGION,
            region.issue().code()
        );
        assertEquals(
            OrderBatchValidation.ErrorCode.NEGATIVE_AMOUNT,
            negative.issue().code()
        );
    }

    @Test
    void oneRowGetsFirstFailureByValidationOrder() {
        var outcome = (OrderBatchValidation.Rejected)
            OrderBatchValidation.parse(8L, "BAD,-1,?");

        assertEquals(
            OrderBatchValidation.ErrorCode.INVALID_ID,
            outcome.issue().code()
        );
        // Không khẳng định parser đã thu cả 3 lỗi của cùng một dòng.
    }

    @Test
    void snapshotsCannotBeMutatedByCaller() {
        var report = OrderBatchValidation.collectIssues(
            OrderBatchValidation.sample(), 10
        );

        assertThrows(UnsupportedOperationException.class, () ->
            report.orders().clear()
        );
        assertThrows(UnsupportedOperationException.class, () ->
            report.issueSamples().clear()
        );
    }

    @Test
    void repeatedRunsHaveIndependentResults() {
        var a = OrderBatchValidation.collectIssues(
            OrderBatchValidation.sample(), 10
        );
        var b = OrderBatchValidation.collectIssues(
            OrderBatchValidation.sample(), 10
        );

        assertEquals(a, b);
        assertEquals(2L, a.invalidLines());
        assertEquals(2L, b.invalidLines());
    }

    @Test
    void reportRejectsInvalidSampleLimit() {
        assertThrows(IllegalArgumentException.class, () ->
            OrderBatchValidation.collectIssues(
                OrderBatchValidation.sample(), -1
            )
        );
    }

    @Test
    void nullInputIsAContractErrorNotRowIssue() {
        assertThrows(NullPointerException.class, () ->
            OrderBatchValidation.collectIssues(null, 10)
        );
        assertThrows(NullPointerException.class, () ->
            OrderBatchValidation.parse(1L, null)
        );
        assertThrows(NullPointerException.class, () ->
            OrderBatchValidation.collectIssues(
                Arrays.asList("O-101,1,HN", null), 10
            )
        );
    }

    @Test
    void acceptedTotalDetectsOverflow() {
        var report = OrderBatchValidation.collectIssues(
            List.of(
                "O-101," + Long.MAX_VALUE + ",HN",
                "O-102,1,HN"
            ),
            10
        );

        assertEquals(2L, report.validLines());
        assertThrows(ArithmeticException.class, () ->
            report.acceptedTotalCents()
        );
    }
}
```

### 16.1. Test cần đánh giá đúng ý nghĩa, không chỉ không có exception

Một unit test chỉ khẳng định `collectIssues(...)` không ném lỗi có thể bỏ qua các bug nghiêm trọng: số dòng sai bị đếm thiếu, issue đầu tiên bị ghi nhầm số dòng, danh sách lỗi bị cắt nhưng UI không cảnh báo.

Các assertion nên đối chiếu ít nhất:

- Bất biến tổng số dòng.
- Số bản ghi hợp lệ và tổng số lỗi.
- Mã lỗi của từng trường hợp dự kiến.
- Thứ tự issue khi yêu cầu hiển thị theo số dòng.
- Giới hạn mẫu và bộ đếm đầy đủ.
- Tính không sửa đổi của kết quả.
- Sự khác nhau giữa file/nguồn rỗng và lỗi ở nguồn.

### 16.2. Không viết test bắt parallel fail-fast luôn trả lỗi có số dòng nhỏ nhất

Một parallel pipeline có thể quan sát và ném ngoại lệ từ phân đoạn khác trước. Unit test muốn xác định **dòng lỗi đầu tiên theo số dòng** nên dùng pipeline tuần tự hoặc thu kết quả rồi sắp theo `lineNumber`. Đừng làm test phụ thuộc scheduling rồi coi nó là hợp đồng của API.

### 16.3. Các phép thử tích hợp thêm

Khi chuyển ví dụ sang tệp thật, nên có test với thư mục tạm:

- File rỗng hợp lệ.
- File không tồn tại: lỗi I/O, không tạo báo cáo rỗng.
- File có charset không đúng hoặc dòng CSV quoted phức tạp.
- Một reader giả lập `IOException` giữa chừng.
- File rất lớn với `sampleLimit` nhỏ để kiểm chứng giới hạn lưu issue.
- Import không ghi database khi `invalidLines > 0` theo quality gate.

Đây là những phép thử **ngoài code JUnit minh họa** nếu cần kết nối tới I/O hoặc repository thật.

## 17. Khi nào dùng `partitioningBy`, `teeing` hoặc collector chuyên biệt?

### 17.1. `partitioningBy` trên một danh sách outcome đã materialize

Nếu đã có `List<ParseOutcome> outcomes`, có thể phân tách nhanh hai phía bằng:

```java
Map<Boolean, List<OrderBatchValidation.ParseOutcome>> parts =
    outcomes.stream().collect(
        java.util.stream.Collectors.partitioningBy(
            outcome ->
                outcome instanceof OrderBatchValidation.Accepted
        )
    );
```

Phía `true` là accepted; phía `false` còn **cả Blank lẫn Rejected**. Vì vậy, không được kết luận `parts.get(false).size()` là số lỗi. Bạn vẫn phải phân loại Blank và Rejected ở bước sau.

`partitioningBy` ngắn gọn khi chỉ có hai trạng thái, nhưng trường hợp bài này có **ba loại outcome** và cần giữ counts/issues, nên collector tùy chỉnh rõ ràng hơn.

### 17.2. `teeing` khi hai downstream độc lập là đủ

`Collectors.teeing` (Java 12+) gửi mỗi phần tử đến hai downstream collector rồi kết hợp kết quả. Ví dụ, từ một stream `Accepted` đã được validate:

```java
record CountAndSum(long count, long sumCents) {}

CountAndSum stats = validOrders.stream().collect(
    java.util.stream.Collectors.teeing(
        java.util.stream.Collectors.counting(),
        java.util.stream.Collectors.summingLong(
            OrderBatchValidation.Order::amountCents
        ),
        CountAndSum::new
    )
);
```

Đây là đoạn dùng biến `validOrders` có kiểu `List<OrderBatchValidation.Order>`. `teeing` phù hợp khi chỉ cần kết hợp hai phép tổng hợp, nhưng không tự định nghĩa đầy đủ ba trạng thái parse, số dòng hay chính sách mẫu lỗi. `summingLong` không tự phát hiện overflow; nếu cần số học kiểm tra tràn, dùng accumulator thích hợp như ví dụ `Math.addExact`.

### 17.3. Validation library khi số lượng quy tắc tăng mạnh

Khi dữ liệu có hàng chục trường và yêu cầu **gom mọi lỗi trên cùng một dòng**, một thư viện validation hoặc mô hình `Validated<T>` với `List<FieldIssue>` có thể diễn đạt tốt hơn một chuỗi `if` trong parser. Nhưng dù sử dụng thư viện nào, vẫn phải giữ ranh giới:

```text
Lỗi có thể dự đoán từ dữ liệu → validation issue
Lỗi infrastructure/runtime      → failure riêng
Kết quả đã validate             → có thể bước sang side effect
```

Không để việc đổi abstraction khiến lỗi I/O hay lỗi lập trình bị nuốt thành “dữ liệu rỗng”.

## 18. Quyết định cuối: dừng ngay, báo mọi lỗi hay chấp nhận một phần?

Hai hệ thống có thể dùng **cùng một parser** nhưng quyết định khác nhau khi nhận `BatchReport`.

### 18.1. Thanh toán hoặc sổ cái: validate hết, chặn ghi nếu có lỗi

Giả sử nguồn chứa giao dịch tài chính. Một khoản bị bỏ qua có thể làm tổng không cân. Chính sách phù hợp có thể là:

```text
Parse/validate tất cả dòng
     │
     ├─ Có issue?          → REJECT batch, không gọi payment API.
     ├─ Có batch issue?    → REJECT batch, không ghi DB.
     └─ Không có lỗi?      → Tạo kế hoạch và thực thi có transaction policy.
```

Ở đây, **thu thập lỗi** giúp người dùng sửa nhiều vấn đề cùng lúc, còn **fail trước khi ghi** bảo vệ dữ liệu nghiệp vụ. Đây là hai quyết định ở hai ranh giới, không mâu thuẫn nhau.

### 18.2. Log vận hành: skip-with-count và cảnh báo

Với log không dùng làm sổ cái, có thể cho phép một tỷ lệ dòng lỗi nhưng phải báo:

```text
valid=99.500
invalid=500
blank=20
issueSamples=10
quality=WARNING
```

Báo cáo chỉ đại diện cho **99.500 sự kiện hợp lệ**; nó không phải một mô tả đầy đủ của mọi dòng. Không dùng số kết quả hợp lệ để khẳng định không có dòng mất do lỗi đọc file.

### 18.3. API đồng bộ: trả lỗi đầu tiên hay nhiều lỗi?

Một API nhập một bản ghi có thể trả lỗi đầu tiên dưới dạng:

```text
HTTP 400 / VALIDATION_ERROR
field=amountCents, code=NEGATIVE_AMOUNT
```

Một API nhập batch có thể trả nhiều lỗi:

```text
validationStatus=REJECTED
totalLines=7
invalidLines=2
issues=[line 3 FIELD_COUNT, line 5 NEGATIVE_AMOUNT]
```

Mã HTTP, payload và số lỗi tối đa được công bố phải theo hợp đồng API cụ thể. Đừng âm thầm thay đổi một endpoint “lỗi đầu tiên” thành “trả partial success” chỉ vì mới dùng collector.

### 18.4. Khi nào cần hai lượt xác thực?

Nếu hệ thống chỉ được ghi sau khi **toàn bộ tệp rất lớn** được kiểm tra, một lựa chọn là:

1. **Pass 1:** parse để kiểm đếm và phát hiện lỗi, ghi kết quả validation vào staging, không gọi dịch vụ ngoài.
2. **Quality gate:** yêu cầu không có lỗi và thỏa điều kiện batch.
3. **Pass 2/execution:** đọc từ **snapshot/staging bất biến đã xác thực**, tạo command và ghi qua coordinator.

Không được đọc một file đang bị thay đổi giữa hai lượt rồi coi pass 1 đã xác thực chính xác dữ liệu pass 2. Cần snapshot, checksum, version hoặc cơ chế cố định nguồn phù hợp. Nếu không có khả năng cố định nguồn và yêu cầu all-or-nothing, thiết kế phải giải quyết rủi ro này trước khi thực thi.

## 19. Những phản mẫu thường gặp

| Phản mẫu | Hậu quả | Hướng sửa |
| --- | --- | --- |
| `parseOrNull` rồi `filter(Objects::nonNull)` | Mất count và nguyên nhân lỗi | Trả `ParseOutcome` tường minh |
| `catch (Exception) { return Optional.empty(); }` | Che lỗi lập trình, I/O và dịch vụ | Chỉ bắt lỗi dữ liệu dự kiến |
| `anyMatch(isInvalid)` rồi báo đã thu mọi lỗi | Short-circuit bỏ phần tử còn lại | Dùng collector nếu cần mọi issue |
| Fail-fast song song rồi tin exception là dòng lỗi nhỏ nhất | Phụ thuộc thứ tự thực thi | Dùng tuần tự hoặc sắp các issue |
| Ghi DB trong `map` trước validation hoàn tất | Có thể ghi một phần rồi gặp dòng sai | Chuẩn bị/validate trước, ghi sau |
| `peek(audit::save)` | Audit có thể không được gọi như mong đợi | Ghi tại ranh giới action tường minh |
| Dùng chung `ArrayList` ngoài collector trong `parallelStream` | Race và dữ liệu không xác định | Collector sở hữu state cục bộ, combiner đúng |
| Khai `CONCURRENT` cho collector có `ArrayList` thường | Nhiều thread có thể sửa cùng container | Không khai sai characteristic |
| Giới hạn 10 issue rồi hiển thị “có 10 lỗi” | Che tổng số lỗi thực | Dùng `invalidLines`, ghi “10 mẫu” |
| Bắt `UncheckedIOException` như dòng sai schema | Che việc file chưa đọc hết | Báo lỗi nguồn và trạng thái partial riêng |
| Dùng `List.copyOf` rồi tin đã deep-copy mọi object | Phần tử mutable vẫn có thể đổi | Dùng value object/defensive copy |
| Cho rằng tổng tiền bằng 0 nghĩa là không có đơn | Đơn hợp lệ có amount 0 | Giữ cả count và sum |
| Chỉ kiểm tra duplicate trong parser một dòng | Không thấy trùng giữa hai dòng | Validation cấp batch |
| Thu mọi `Order` và mọi lỗi của file vô hạn | Có thể hết bộ nhớ | Chunk/staging, accumulator gọn và giới hạn mẫu |
| Đổi `sampleLimit` thành 0 rồi gọi “không có lỗi” | Nhầm danh sách rỗng với tổng lỗi bằng 0 | Kiểm tra `invalidLines` |
| Chỉ kiểm thử “không có exception” | Bỏ qua tính đúng của số liệu và chính sách | Assert bất biến, codes, line numbers |

### 19.1. Vì sao phải đặt tên chính sách rõ ràng?

`skipInvalidRecords`, `bestEffort` và `tolerant` là những tên dễ gây hiểu nhầm nếu không mô tả:

- Dòng trắng có tính là lỗi không?
- Có giữ mọi lỗi hay chỉ mẫu?
- Có cho phép ghi những record hợp lệ khi còn lỗi không?
- Có dừng ngay ở lỗi I/O không?
- Có thu thập lỗi ở cấp batch không?

Một API tốt có tài liệu về **giới hạn bảo đảm** thay vì dựa vào một tên ngắn mơ hồ.

## 20. Bài tập thực hành

### Bài 1 — Chọn chính sách cho ba nghiệp vụ

Hãy đề xuất chính sách lỗi cho:

1. Import các bút toán kế toán bắt buộc cân bằng.
2. Kiểm tra CSV cho người dùng chỉnh sửa trước khi import.
3. Tổng hợp log vận hành với vài dòng lỗi nhưng cần cảnh báo.

Nêu loại báo cáo trả về, có được gọi repository khi `invalidLines > 0` hay không, và lý do.

### Bài 2 — Mở rộng parser để thu mọi lỗi của một dòng

Thay `Rejected(RowIssue)` bằng `Rejected(List<FieldIssue>)`. Với dòng `BAD,-1,?`, trả ít nhất ba lỗi trường tương ứng `id`, `amountCents` và `region`. Vẫn giữ một bộ đếm **invalidLines tăng một lần cho dòng ấy**, không tăng ba lần chỉ vì có ba field issues.

### Bài 3 — Fail-fast chính xác theo dòng

Tạo nguồn 100 dòng có lỗi tại dòng 10 và dòng 50. Dùng sequential stream và chứng minh `validateFailFast` báo dòng 10. Sau đó thử nghiệm một phiên bản parallel; giải thích vì sao **không** nên viết assertion bắt exception từ parallel version luôn là dòng 10.

### Bài 4 — Giới hạn 5 mẫu lỗi

Tạo 10.000 dòng sai, chạy `collectIssues(lines, 5)`. Kiểm thử:

- `invalidLines == 10_000`.
- `issueSamples.size() == 5`.
- Số dòng của năm mẫu phù hợp thứ tự nguồn.
- Các chỉ số khác vẫn chính xác.

Giải thích vì sao vấn đề bộ nhớ của **`orders`** vẫn còn nếu file có hàng triệu dòng hợp lệ.

### Bài 5 — Phân biệt nguồn rỗng, nguồn lỗi và dữ liệu sai

Viết test cho ba tình huống:

1. Một file trống nhưng đọc được.
2. File không tồn tại.
3. File đọc được và chỉ chứa các dòng sai.

Không để cả ba trường hợp trả một `BatchReport` rỗng giống nhau.

### Bài 6 — Duplicate ID ở cấp batch

Cho hai dòng hợp lệ cùng `orderId` nhưng khác vùng. Bổ sung bước kiểm tra duplicate sau parsing, trả `BatchIssue` phù hợp. Nếu cần báo số dòng của cả hai bản ghi, sửa cấu trúc intermediate để giữ nguồn gốc `Accepted.lineNumber`.

### Bài 7 — Tổng tiền và overflow

Tạo hai dòng hợp lệ: một có amount `Long.MAX_VALUE` và một có amount `1`. Kiểm chứng `parse` chấp nhận cả hai, nhưng `acceptedTotalCents` ném `ArithmeticException`. Viết phương án cộng bằng `BigInteger` nếu hệ thống thật yêu cầu phạm vi lớn hơn.

### Bài 8 — Chặn side effect trước quality gate

Tạo một fake repository ghi nhận số lần gọi `save`. Với `BatchReport.invalidLines > 0`, coordinator **không được** gọi repository. Với report sạch và qua validation cấp batch, gọi repository theo một policy rõ ràng. Test số lần gọi và phân biệt lỗi lưu với lỗi parser.

### Bài 9 — Hiển thị lỗi cho người dùng

Thiết kế DTO API có:

```text
totalLines, validLines, blankLines, invalidLines,
issueSamples, samplesTruncated, validationDecision
```

Khi `invalidLines > issueSamples.size()`, yêu cầu hiển thị “Đang hiển thị N trên M lỗi” thay vì chỉ “có N lỗi”.

### Bài 10 — Dùng collector với nguồn không có thứ tự

Thử dùng một `Set` hoặc pipeline `unordered()` làm nguồn. Nếu báo cáo cần “năm issue đầu tiên”, hãy định nghĩa **tiêu chí thứ tự** (ví dụ `lineNumber` tăng dần) trước khi chọn mẫu. Giải thích tại sao khái niệm “đầu tiên” vô nghĩa nếu không có thứ tự đáng tin.

### Bài 11 — Validation hai pha cho file lớn

Mô tả hai pha validation và execution dùng staging:

- Làm sao bảo đảm dữ liệu không thay đổi giữa hai pha?
- Khi parser gặp lỗi thì cleanup staging thế nào?
- Nếu tiến trình crash sau validation nhưng trước execution, làm sao resume?
- Nếu execution đã ghi một phần thì báo cáo trạng thái nào?

Không coi một phép `collect` thành transaction phân tán.

### Bài 12 — So sánh `partitioningBy` và collector tùy chỉnh

Tạo `List<ParseOutcome>` trước, sau đó dùng `partitioningBy` để chia accepted với phần còn lại. Chỉ ra vì sao phía còn lại gồm **Blank + Rejected**. So sánh chi phí nhớ hai lượt duyệt với collector duy nhất chỉ giữ counters và mẫu lỗi.

## 21. Checklist thiết kế và tổng kết

Trước khi đưa logic import hoặc validation vào hệ thống thật, kiểm tra:

- [ ] Schema dữ liệu và cách phân biệt dòng trắng đã công bố.
- [ ] Lỗi dữ liệu dự kiến có mã riêng, không bắt `Exception` quá rộng.
- [ ] Có quyết định rõ **FAIL_FAST** hay **COLLECT/COUNT**.
- [ ] Nếu thu lỗi, biết đang thu **mọi dòng lỗi** hay chỉ **lỗi mẫu**.
- [ ] Có bộ đếm đầy đủ `total/valid/blank/invalid` và bất biến đối chiếu.
- [ ] Gắn số dòng theo vị trí nguồn, không bằng shared-state mapper song song.
- [ ] Đã xử lý quy tắc giữa nhiều dòng, ví dụ duplicate ID.
- [ ] Có quality gate trước khi gọi dịch vụ hoặc ghi database.
- [ ] Ngoại lệ I/O không bị chuyển thành dòng sai hoặc báo cáo rỗng.
- [ ] Nguồn từ `Files.lines` được đóng bằng `try-with-resources`.
- [ ] Bộ nhớ của `orders`, `issues` và kích thước tệp đã được cân nhắc.
- [ ] Không dựa vào việc parallel fail-fast luôn trả lỗi có số dòng nhỏ nhất.
- [ ] Collector không chia sẻ state mutable sai cách và có combiner hợp lệ.
- [ ] Không để raw line/error message làm lộ dữ liệu nhạy cảm.
- [ ] Đã kiểm thử cả trường hợp lỗi, nguồn rỗng, mẫu bị cắt và overflow.

| Câu hỏi | Lựa chọn phù hợp |
| --- | --- |
| Một dòng sai phải chặn ngay phép xử lý? | **Fail-fast** trên ordered sequential stream |
| Muốn người dùng sửa nhiều lỗi trong một lần? | **Collect errors** và trả report có cấu trúc |
| Tệp lớn, cần giới hạn bộ nhớ lỗi? | **Count all + bounded issue samples** |
| Cần xem mọi lỗi trường trong một dòng? | `Rejected(List<FieldIssue>)` |
| Có ba loại `Accepted/Blank/Rejected`? | Kiểu outcome riêng, không ép vào `Optional.empty()` |
| Chỉ cần biết có lỗi hay không? | Short-circuit `anyMatch` có thể đủ, nhưng **không** liệt kê lỗi |
| Cần giữ thứ tự số dòng chính xác? | Nguồn đánh số theo vị trí và collector ordered hoặc sort cuối |
| Cần tránh ghi partial data? | Parse/validate và **quality gate** trước side effect |
| Cần báo kết quả kỹ thuật và quyết định xuất bản? | Tách `BatchReport` và `ValidationDecision` |
| Nguồn là file rất lớn? | Reader/chunk/staging, không tùy tiện `toList()` |
| Có lỗi mở/đọc file? | Truyền lỗi I/O, không tạo report thành công giả |

### Kết luận

**Chọn dừng khi có lỗi hoặc thu thập lỗi cùng kết quả** không đơn thuần là đổi từ `throw` sang `catch`. Đây là quyết định về **nghĩa của dữ liệu**: khi nào một kết quả được xem là đầy đủ, khi nào chỉ là preview, và khi nào có quyền tạo tác dụng phụ bên ngoài.

Với **JAVA_STREAM_API**, hãy giữ parser thuần để chuyển từng phần tử thành một outcome rõ ràng; chọn fail-fast khi cần từ chối ngay trên nguồn tuần tự; dùng collector có state thuộc quyền sở hữu của pipeline khi cần gom cả giá trị hợp lệ, bộ đếm và lỗi mẫu. Sau bước thu thập, kiểm tra quy tắc cấp batch rồi đưa ra quyết định ghi dữ liệu tường minh. Nhờ vậy, các phép `filter`, `map`, `reduce` và `collect` vừa dễ kiểm thử, vừa không vô tình che lỗi hoặc biến một báo cáo thiếu thành thành công giả.
