# Schema version của input trong Spring Batch

## 1. Vì sao cần quản lý phiên bản schema của dữ liệu đầu vào?

Một Spring Batch job có thể nhận dữ liệu từ file CSV, JSON/NDJSON, XML, Avro, Parquet, database staging, hoặc thông điệp được xuất theo lô từ hệ thống khác. Trong khi job vẫn hoạt động, **cấu trúc input có thể thay đổi**: thêm cột, đổi tên trường, đổi kiểu dữ liệu, thay quy ước ngày tháng hoặc bổ sung giá trị mới cho một trường trạng thái.

Giả sử job `importOrdersJob` đang đọc file CSV:

```csv
# schema-version: v1
order_id,customer_id,amount
ORD-001,CUS-10,125000
ORD-002,CUS-11,320000
```

Một hệ thống nguồn được nâng cấp và bắt đầu xuất:

```csv
# schema-version: v2
order_id,customer_id,amount,currency
ORD-001,CUS-10,125000,VND
ORD-002,CUS-11,320000,VND
```

Nếu reader cũ vẫn giả định mỗi dòng có đúng ba trường, có thể xảy ra nhiều kết quả: parser báo lỗi số cột, cột bị ánh xạ sai, hoặc trường mới bị bỏ qua mà không ai biết. Với thay đổi phức tạp hơn như đổi `amount` thành `net_amount`, job thậm chí có thể **xử lý thành công về mặt kỹ thuật nhưng cho kết quả nghiệp vụ sai**.

**Schema version của input** là mã phiên bản gắn với hợp đồng dữ liệu mà bên gửi và bên nhận cùng hiểu. Nó cho phép batch job quyết định một input có được hỗ trợ hay không, chọn đúng quy tắc parse/validate, chuyển dữ liệu về mô hình thống nhất và lưu dấu vết phục vụ đối soát hoặc chạy lại.

```text
Hệ thống nguồn
    |
    +-- Input + schemaVersion + metadata / manifest
                     |
                     v
               Preflight validation
               - Xác định version
               - Kiểm tra hợp đồng
               - Xác minh file ổn định
                     |
             +-------+-------+
             |               |
          Hợp lệ         Không hỗ trợ / sai
             |               |
             v               v
      Reader theo version   Reject / Quarantine
             |
             v
      Mô hình chuẩn hóa (canonical model)
             |
             v
      Processor / Writer / JobRepository
```

Điểm quan trọng: schema version của **input nghiệp vụ** khác với version của **các bảng `BATCH_*`** trong `JobRepository` và khác với version migration của database. Cả ba có thể cùng tồn tại trong một ứng dụng, nhưng phục vụ các hợp đồng riêng.

## 2. Schema bao gồm những gì?

Không nên hiểu schema chỉ là danh sách tên cột. Trong pipeline dữ liệu, cần phân biệt ít nhất ba lớp:

| Lớp hợp đồng | Nội dung | Ví dụ lỗi |
|---|---|---|
| **Vật lý/cú pháp (physical/syntax)** | Encoding, delimiter, quote/escape, thứ tự cột, file header, JSON object shape, kiểu primitive | File CSV dùng `;` thay cho `,`; trường số bị parse nhầm. |
| **Cấu trúc (structural)** | Trường bắt buộc/tùy chọn, kiểu dữ liệu, độ dài, độ chính xác, tập trường được hỗ trợ | Thiếu `customer_id`, `amount` chuyển từ số sang chuỗi không theo quy ước. |
| **Ngữ nghĩa (semantic)** | Ý nghĩa trường, đơn vị đo, timezone, business rule, phạm vi giá trị, mặc định | `amount` đổi từ VND sang đơn vị nghìn VND mà tên cột giữ nguyên. |

Hai file cùng có header `order_id,amount` chưa chắc tương thích. Nếu phiên bản mới đổi quy tắc `amount` từ đơn vị đồng sang nghìn đồng, reader cũ có thể không lỗi nhưng ghi dữ liệu sai hàng nghìn lần. **Thay đổi ngữ nghĩa cần được ghi nhận trong hợp đồng/version**, ngay cả khi cấu trúc không thay đổi.

Một bản mô tả schema hữu ích thường chứa:

1. Tên dataset hoặc event type (`orders`, `customers`, `payments`).
2. `schemaVersion` cụ thể (`v1`, `v2`, `2026-11`...) và phạm vi áp dụng.
3. Định dạng, encoding, delimiter và chính sách escape/quote.
4. Danh sách trường: tên, kiểu, bắt buộc hay tùy chọn, giới hạn và default.
5. Ý nghĩa nghiệp vụ: đơn vị tiền, timezone, enum và cách diễn giải null.
6. Những thay đổi so với phiên bản trước và chính sách tương thích.
7. Cách nhận diện version, hành vi khi thiếu version và thời hạn hỗ trợ.
8. Quy tắc kiểm tra input và xử lý file không hợp lệ.

## 3. Ví dụ tiến hóa schema: v1, v2 và v3

Giả sử một nhà cung cấp gửi file đơn hàng. Hợp đồng thay đổi như sau:

| Version | Cấu trúc | Quy tắc | Tình trạng |
|---|---|---|---|
| `v1` | `order_id,customer_id,amount` | Theo hợp đồng v1, `amount` luôn là VND. | Được hỗ trợ trong giai đoạn chuyển tiếp. |
| `v2` | Thêm cột bắt buộc `currency` | `amount` mang đơn vị được chỉ định bởi `currency`. | Phiên bản khuyến nghị. |
| `v3` | Đổi `amount` thành `net_amount`, thêm `tax_amount` | Tổng tiền được tính từ hai trường theo quy tắc v3. | Cần parser/mapper mới. |

Trong code xử lý nghiệp vụ, ta muốn đưa các biến thể về một mô hình chung:

```java
import java.math.BigDecimal;

public record NormalizedOrder(
        String orderId,
        String customerId,
        BigDecimal amount,
        String currency) {
}
```

Ví dụ mapping:

```text
Input v1: order_id=ORD-001, amount=125000
    -> NormalizedOrder("ORD-001", ..., 125000, "VND")

Input v2: order_id=ORD-001, amount=125000, currency=VND
    -> NormalizedOrder("ORD-001", ..., 125000, "VND")

Input v3: net_amount=120000, tax_amount=5000, currency=VND
    -> NormalizedOrder("ORD-001", ..., 125000, "VND")
```

Quy tắc cộng `net_amount + tax_amount` chỉ là **giả định nghiệp vụ của ví dụ**. Nếu hai trường không cùng nghĩa với `amount` cũ, không được tự cộng rồi xem như tương đương. Việc chuẩn hóa phải xuất phát từ data contract chính thức của nguồn.

**Vì sao chuẩn hóa trước processor?** Processor, writer và logic đối soát có thể làm việc với `NormalizedOrder` thay vì có những nhánh điều kiện `if (v1)`, `if (v2)` rải rác trong toàn bộ pipeline. Mã tương thích schema được tập trung tại ranh giới input, giúp giảm khả năng xử lý nhầm các phiên bản.

## 4. Backward compatibility và forward compatibility

Khi nhận dữ liệu từ nhiều phiên bản, cần xác định rõ tương thích theo hướng nào.

- **Backward compatible:** reader/consumer **mới** có thể đọc dữ liệu được ghi theo schema **cũ**.
- **Forward compatible:** reader/consumer **cũ** có thể đọc dữ liệu được ghi theo schema **mới**.
- **Full compatible:** cả hai hướng trên cùng đúng trong giới hạn chính sách đã công bố.

Hai khái niệm này được sử dụng trong nhiều hệ thống schema registry. Khả năng tương thích thực sự còn phụ thuộc định dạng, parser, default, cách xử lý trường không biết và business rule; không thể suy ra chỉ từ việc “đã thêm một cột”.

| Thay đổi | Khả năng tương thích thường gặp | Điều cần xác minh |
|---|---|---|
| Thêm trường tùy chọn có default rõ ràng | Dễ hỗ trợ backward compatibility | Reader cũ có bỏ qua trường lạ không? Consumer mới có fallback cho dữ liệu cũ không? |
| Thêm trường bắt buộc không có default | Thường phá backward compatibility | Input cũ không có giá trị cho trường mới. |
| Đổi tên/xóa trường bắt buộc | Thường là breaking change | Có alias hoặc migration layer không? |
| Đổi kiểu `String` sang số | Có thể phá tương thích | Giá trị cũ có parse được? Null/empty được diễn giải thế nào? |
| Đổi `Long` sang decimal | Tùy format và consumer | Precision, rounding, scale và representation. |
| Thêm enum value | Có thể làm consumer cũ thất bại | Xử lý unknown enum/giá trị dự phòng. |
| Thêm cột CSV ở cuối | Phụ thuộc parser | Reader strict có thể từ chối số cột mới. |
| Đổi thứ tự cột CSV | Có thể gây sai âm thầm | Reader ánh xạ theo vị trí hay tên header? |
| Đổi timezone/đơn vị đo nhưng giữ kiểu | Thay đổi ngữ nghĩa quan trọng | Cần version và conversion rule tường minh. |

Ví dụ `v2` thêm `currency` không tự động tương thích với reader `v1`. Nếu reader dùng `DelimitedLineTokenizer` ở chế độ strict và mong ba cột, nó có thể báo lỗi khi nhận bốn giá trị. Nếu reader bỏ qua cột mới nhưng `amount` đã được phép chứa USD, nó còn có thể **ghi sai đơn vị** dù parser không lỗi.

### 4.1. Chính sách hỗ trợ phiên bản

Một đội phát triển có thể công bố:

```text
Dataset: orders
Current schema: v2
Accepted inputs: v1, v2
Rejected inputs: unknown, v0, v3 chưa được triển khai
v1 deprecation date: theo kế hoạch đã thống nhất
```

Khi còn hỗ trợ `v1`, cần có test chứng minh cả `v1` và `v2` được chuyển sang cùng canonical model đúng nghiệp vụ. Nếu gỡ hỗ trợ `v1`, cần thông báo trước và tạo đường chuyển đổi hoặc điều kiện từ chối rõ ràng. Không nên để phiên bản “tự hết hạn” chỉ vì code mới vô tình không parse được file cũ.

## 5. Cách xác định `schemaVersion` của input

Có nhiều vị trí có thể chứa metadata phiên bản; hãy chọn một cách tường minh và kiểm chứng được.

### 5.1. Header trong file

Ví dụ CSV có hai dòng metadata/header:

```csv
# schema-version: v2
order_id,customer_id,amount,currency
ORD-101,CUS-44,150000,VND
```

Ưu điểm: version đi cùng nội dung; một file tự mô tả được hợp đồng. Nhược điểm: dòng đầu có thể không tuân theo chuẩn CSV thông thường, nên reader cần được cấu hình bỏ qua dòng metadata; cần quy định rõ xử lý BOM, whitespace, encoding, ký tự xuống dòng và comment marker.

Ví dụ JSON một document:

```json
{
  "schemaVersion": "v2",
  "dataset": "orders",
  "records": [
    {"orderId": "ORD-101", "customerId": "CUS-44", "amount": 150000, "currency": "VND"}
  ]
}
```

Đối với file rất lớn, không nên buộc phải nạp toàn bộ mảng `records` vào bộ nhớ chỉ để đọc version. Có thể chọn **NDJSON + manifest** hoặc một envelope có khả năng streaming phù hợp, tùy định dạng và reader.

### 5.2. Manifest hoặc metadata bên ngoài file

Ví dụ `orders-2026-11-16.manifest.json`:

```json
{
  "dataset": "orders",
  "schemaVersion": "v2",
  "objectKey": "staging/orders/2026-11-16/orders.csv",
  "sha256": "<sha256-hex-of-file>",
  "encoding": "UTF-8",
  "format": "CSV",
  "recordCount": 1200000
}
```

Chuỗi `<sha256-hex-of-file>` trong ví dụ chỉ là placeholder; khi vận hành cần digest thật. Manifest hữu ích khi file dữ liệu không cho phép thêm header, cần lưu checksum, độ lớn, thời điểm xuất hoặc hợp đồng nhiều file cùng một lần chuyển giao.

Một số hệ thống lưu version trong object storage metadata, database staging batch record hoặc schema registry. Dù nguồn ở đâu, cần kiểm tra **metadata thuộc đúng phiên bản vật lý của object** đang đọc. Ví dụ, cùng một object path có thể bị ghi đè sau khi job bắt đầu. Hệ thống lưu trữ có `versionId` hoặc immutable key giúp giảm nguy cơ đọc nhầm object mới.

### 5.3. Schema registry và định dạng có schema đi kèm

Avro/Protobuf và một số giao thức sự kiện có thể dùng schema ID/fingerprint cùng schema registry; định dạng container như Avro Object Container File cũng có thể mang schema writer. Batch cần xác định **writer schema** của input và **reader schema** ứng dụng hỗ trợ, rồi dùng quy tắc tương thích phù hợp.

Điều này khác với việc tự giải thích số `v2` trong CSV. Khi sử dụng registry, nên dựa vào schema ID/phân giải schema chính thức thay vì suy ra từ tên file. Cần quản lý cả khả năng registry không truy cập được và chiến lược cache schema ở môi trường kiểm thử/chạy thật.

### 5.4. Không suy đoán version từ dữ liệu khi có hợp đồng tường minh

Những cách như “nếu có bốn cột là v2, ba cột là v1” hoặc “nếu file name chứa `_v2` thì dùng v2” có thể hỗ trợ quá trình chuyển tiếp **khi được thống nhất thành quy tắc chính thức**, nhưng dễ sai nếu thêm trường, thay header, file có dòng lỗi hoặc nguồn đổi tên file.

Ưu tiên version trong manifest/header/registry được kiểm chứng. Nếu bắt buộc phải suy đoán cho dữ liệu legacy, hãy cô lập logic ấy thành một bước detection có test riêng và **từ chối** khi không thể phân biệt rõ ràng.

## 6. Kiểm tra đầu vào trước khi chạy chunk (preflight validation)

Một batch job thường cần phân biệt lỗi **toàn bộ file không phù hợp với hợp đồng** và lỗi **một vài bản ghi bên trong file**.

```text
File vừa được nhận
    |
    +-- Kiểm tra nguồn, tên/object key, kích thước, checksum
    +-- Đọc metadata/manifest/schema ID
    +-- Xác nhận version được hỗ trợ
    +-- Kiểm tra header, encoding, delimiter, field types bắt buộc
    +-- Xác định input revision bất biến
    |
    +-- Thất bại -> reject toàn file, không chạy writer
    |
    +-- Đạt -> bắt đầu đọc và validate từng record
                 |
                 +-- Record hợp lệ -> processor/writer
                 +-- Record lỗi -> skip/quarantine/fail theo policy
```

Một số nguyên tắc:

1. **Unknown schema version là lỗi file-level.** Đừng để reader âm thầm dùng parser mặc định rồi “thử xem có chạy không”.
2. **Schema mismatch là lỗi hợp đồng.** Với CSV strict, header khác với phiên bản đã công bố nên được phát hiện trước khi ghi dữ liệu nghiệp vụ.
3. **Record-level lỗi là vấn đề khác:** giá trị số không parse được, ngày sai định dạng, enum không hợp lệ hoặc giá trị rỗng có thể xử lý theo skip/quarantine policy.
4. **Preflight đầy đủ có thể tốn chi phí:** đọc header thường rẻ; checksum SHA-256 của một file hàng trăm GB yêu cầu quét nội dung. Chọn thời điểm/hash strategy phù hợp và không giả định object storage ETag luôn là SHA-256 của nội dung.
5. **Không tin nguồn metadata một cách mù quáng:** manifest báo `v2` nhưng header thực tế là `v1` là dấu hiệu sai hợp đồng. Phải có hành vi từ chối rõ ràng.

Với pipeline mà bản ghi bị reject **không được phép xuất hiện trong dữ liệu đã publish**, có thể dùng mô hình `validate -> stage -> promote/publish` để kiểm tra trước khi công bố kết quả. Nếu yêu cầu là atomic ở mức cả file, chỉ kiểm tra header rồi bắt đầu commit từng chunk sẽ không đáp ứng được: các chunk đầu có thể đã được commit trước khi một dòng lỗi ở cuối file được phát hiện.

## 7. Cài đặt preflight cho hai phiên bản CSV

Ví dụ này sử dụng **Java 17+, Spring Batch 5.x, Spring Boot 3.x và JUnit 5**. Các API Java core có thể dùng độc lập; các class Spring Batch thay đổi package ở dòng 6.x nên cần đối chiếu phiên bản thực tế.

### 7.1. Định nghĩa chính sách phiên bản và header

Ta nhận `v1` và `v2` với header chính xác theo hợp đồng. Trong ví dụ, dòng đầu tiên phải là `# schema-version: vN` và dòng thứ hai là header CSV.

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

public final class OrderSchemaPreflight {

    private static final String VERSION_PREFIX = "# schema-version: ";

    private static final Map<String, List<String>> ALLOWED_COLUMNS = Map.of(
            "v1", List.of("order_id", "customer_id", "amount"),
            "v2", List.of("order_id", "customer_id", "amount", "currency")
    );

    public record Result(String version, List<String> columns) {
    }

    public Result inspect(Path inputFile) throws IOException {
        try (BufferedReader input = Files.newBufferedReader(
                inputFile, StandardCharsets.UTF_8)) {

            String marker = input.readLine();
            if (marker == null || !marker.startsWith(VERSION_PREFIX)) {
                throw new IllegalArgumentException(
                        "Missing input schema version marker");
            }

            String version = marker.substring(VERSION_PREFIX.length()).trim();
            List<String> expectedColumns = ALLOWED_COLUMNS.get(version);
            if (expectedColumns == null) {
                throw new IllegalArgumentException(
                        "Unsupported input schema version: " + version);
            }

            String header = input.readLine();
            String expectedHeader = String.join(",", expectedColumns);
            if (!expectedHeader.equals(header)) {
                throw new IllegalArgumentException(
                        "Header mismatch for schema " + version);
            }

            return new Result(version, expectedColumns);
        }
    }
}
```

Trong ví dụ, `ALLOWED_COLUMNS` xác định policy có thể được quản lý bằng code/test. `inspect(...)` không đọc hàng triệu records; nó kiểm tra metadata và cấu trúc header trước khi job bắt đầu đọc.

**Giới hạn cố ý của ví dụ:** phép so sánh header bằng chuỗi chỉ phù hợp với quy ước header đơn giản và cố định. CSV thật có thể có BOM, tên trường chứa dấu phẩy, quote/escape, khoảng trắng tùy chính sách hoặc nhiều dòng. Khi hợp đồng cho phép những biến thể đó, hãy dùng một CSV parser đúng RFC 4180 hoặc cấu hình tokenizer tương đương. Không tự tách mọi dòng dữ liệu bằng `String.split(",")` nếu giá trị có thể chứa dấu phẩy trong cặp dấu nháy.

### 7.2. Ánh xạ các phiên bản về một mô hình chung

Trong Spring Batch 5.x, `FlatFileItemReader` kết hợp `DefaultLineMapper`, `DelimitedLineTokenizer` và `FieldSetMapper` để đọc dữ liệu CSV. Ở ví dụ này, hai dòng đầu là metadata/header nên được bỏ qua; preflight đã kiểm tra chúng trước đó.

```java
import java.math.BigDecimal;

import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.mapping.DefaultLineMapper;
import org.springframework.batch.item.file.transform.DelimitedLineTokenizer;
import org.springframework.core.io.FileSystemResource;

public final class OrderReaderFactory {

    public static FlatFileItemReader<NormalizedOrder> create(
            String inputPath, String schemaVersion) {

        String[] columns = switch (schemaVersion) {
            case "v1" -> new String[] {
                    "order_id", "customer_id", "amount"
            };
            case "v2" -> new String[] {
                    "order_id", "customer_id", "amount", "currency"
            };
            default -> throw new IllegalArgumentException(
                    "Unsupported schema: " + schemaVersion);
        };

        DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
        tokenizer.setDelimiter(",");
        tokenizer.setNames(columns);
        tokenizer.setStrict(true);

        DefaultLineMapper<NormalizedOrder> lineMapper =
                new DefaultLineMapper<>();
        lineMapper.setLineTokenizer(tokenizer);
        lineMapper.setFieldSetMapper(fields -> {
            String currency = "v1".equals(schemaVersion)
                    ? "VND" // Default do hợp đồng v1 định nghĩa.
                    : fields.readString("currency");

            return new NormalizedOrder(
                    fields.readString("order_id"),
                    fields.readString("customer_id"),
                    new BigDecimal(fields.readString("amount")),
                    currency);
        });

        FlatFileItemReader<NormalizedOrder> reader =
                new FlatFileItemReader<>();
        reader.setName("orderCsvReader");
        reader.setResource(new FileSystemResource(inputPath));
        reader.setLinesToSkip(2);
        reader.setLineMapper(lineMapper);
        reader.setStrict(true);
        reader.setSaveState(true);
        return reader;
    }
}
```

Kết quả của cả `v1` và `v2` là `NormalizedOrder`. Đoạn code xử lý kiểu dữ liệu cơ bản, nhưng **chưa thực hiện toàn bộ business validation**. Ví dụ, cần kiểm tra `amount >= 0`, currency thuộc danh sách hỗ trợ và `order_id` không rỗng; những quy tắc này nên nằm ở validator/processor phù hợp để có thể kiểm thử độc lập.

`reader.setSaveState(true)` cho phép reader lưu vị trí vào `ExecutionContext` khi được dùng đúng theo vòng đời `ItemStream`. Để restart an toàn, file phải không đổi và tên reader ổn định giữa các lần chạy. Nếu có nhiều reader cùng `ExecutionContext`, đặt `name` khác nhau để tránh trùng khóa trạng thái.

### 7.3. Tạo reader theo `JobParameters` bằng `@StepScope`

Input path và schema version thường khác theo mỗi lần launch job, nên đặt chúng trong `JobParameters` và tạo reader theo step scope:

```java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;

@Bean
@StepScope
FlatFileItemReader<NormalizedOrder> orderReader(
        @Value("#{jobParameters['inputPath']}") String inputPath,
        @Value("#{jobParameters['schemaVersion']}") String schemaVersion) {

    return OrderReaderFactory.create(inputPath, schemaVersion);
}
```

Đoạn trên là phần thân của một class `@Configuration` trong ứng dụng đã bật hỗ trợ Batch. `@StepScope` đảm bảo các giá trị `jobParameters` được resolve khi step chạy, thay vì cố resolve khi `ApplicationContext` khởi động. Không dùng giá trị `schemaVersion` không rõ nguồn để tạo reader: preflight phải đối chiếu với version thực tế của input.

### 7.4. Đưa preflight thành step đứng trước step nhập dữ liệu

Một cách tổ chức flow là có step `validateInputSchema` trước `importOrders`. Nếu version không hợp lệ, job thất bại **trước khi writer xử lý record đầu tiên**.

```java
import java.nio.file.Path;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step validateInputSchemaStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        OrderSchemaPreflight preflight) {

    return new StepBuilder("validateInputSchema", repository)
            .tasklet((contribution, chunkContext) -> {
                JobParameters parameters =
                        contribution.getStepExecution().getJobParameters();

                String inputPath = parameters.getString("inputPath");
                String expectedVersion = parameters.getString("schemaVersion");

                if (inputPath == null || expectedVersion == null) {
                    throw new IllegalArgumentException(
                            "Missing inputPath or schemaVersion");
                }

                OrderSchemaPreflight.Result result =
                        preflight.inspect(Path.of(inputPath));

                if (!expectedVersion.equals(result.version())) {
                    throw new IllegalArgumentException(
                            "JobParameters schemaVersion differs from input");
                }

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

`allowStartIfComplete(true)` trong ví dụ được chọn **có chủ đích**: khi restart một job, validation step đã hoàn thành có thể được chạy lại để kiểm tra version còn đúng. Để bảo vệ dữ liệu thực sự trên restart, phải xác minh thêm **checksum hoặc immutable object revision**, vì header không thay đổi không có nghĩa toàn bộ file vẫn giống lần trước.

Để liên kết flow ở Spring Batch 5.x:

```java
@Bean
Job importOrdersJob(
        JobRepository repository,
        Step validateInputSchemaStep,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", repository)
            .start(validateInputSchemaStep)
            .next(importOrdersStep)
            .build();
}
```

Ở đây `importOrdersStep` là chunk-oriented step do ứng dụng cấu hình dùng reader/writer thích hợp. Hai đoạn là **mẫu cấu hình minh họa**, cần các import `Job`, `JobBuilder`, `Bean` và các bean hạ tầng tương ứng. Để mọi lần chạy reader đều sử dụng chính file đã validate, tránh tự tạo path khác khi reader bắt đầu.

## 8. Cố định schema version và input identity bằng `JobParameters`

Schema version còn ảnh hưởng trực tiếp đến **khả năng restart** của Spring Batch. Một `JobInstance` được xác định bởi tên job và các `JobParameters` có cờ *identifying*. Nếu một job bị lỗi giữa chừng rồi được restart, nó phải biết parser và nguồn dữ liệu của lần chạy ban đầu.

Ví dụ tạo tham số ở nơi nhận file/scheduler:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("inputPath", "/batch/staging/orders-2026-11-16.csv", true)
        .addString("inputRevision", "rev-00042", true)
        .addString("schemaVersion", "v2", true)
        .addString("triggerSource", "scheduler", false)
        .toJobParameters();
```

Các tham số `businessDate`, `inputPath`, `inputRevision`, `schemaVersion` chỉ là **một phương án thiết kế khóa instance**. Trong hệ thống khác, `fileId` hoặc `batchId` bất biến có thể là identifying parameter chính, còn version và checksum là metadata kiểm tra. Quy tắc phải được lựa chọn theo định nghĩa một đơn vị công việc logic, tránh làm nhiều phiên bản parser vô tình tạo nhiều instance xử lý trùng cùng dữ liệu.

Với các tệp rất lớn, có thể gắn `sha256` hoặc object-storage version ID vào manifest và lưu một định danh ổn định trong `JobParameters`. Nếu lưu checksum vào `JobParameters`, hãy cân nhắc độ dài giới hạn/chi phí metadata và không lưu bí mật. **Đường dẫn không đủ chứng minh nội dung bất biến:** file cùng tên có thể bị overwrite sau khi step đã commit một phần.

### 8.1. Restart phải giữ cùng hợp đồng input

```text
Lần đầu:
  JobInstance importOrdersJob / batchId=42
  schemaVersion=v2, inputRevision=rev-00042
  JobExecution #100 -> FAILED ở item thứ 80000

Lần restart:
  Cùng JobInstance / batchId=42
  schemaVersion=v2, inputRevision=rev-00042
  JobExecution #101 -> dùng checkpoint hợp lệ
```

Nếu giữa hai lần chạy, file bị thay bằng phiên bản `v3` nhưng vẫn tên cũ, reader lấy checkpoint `v2` để đọc nội dung `v3` có thể sai hoặc bỏ sót record. Chính sách an toàn là **fail fast khi fingerprint/revision khác**, sau đó quyết định tạo một đợt ingest mới hoặc dựng lại dữ liệu đầu vào đúng revision ban đầu.

Không nên thay `schemaVersion` hoặc thêm `run.id` identifying chỉ để vượt `JobInstanceAlreadyCompleteException` hay `JobExecutionAlreadyRunningException`. Khi muốn xử lý lại một nguồn đã hoàn thành, cần một quy tắc reprocessing riêng, có idempotency và kiểm tra kết quả đã xuất.

### 8.2. Vì sao checksum hoặc immutable revision quan trọng?

Một ví dụ:

```text
10:00 nhận file orders.csv v2, có 100.000 records
10:10 job commit được 60.000 records, sau đó lỗi
10:15 nhà cung cấp ghi đè orders.csv v2 bằng file có thứ tự records khác
10:20 restart từ checkpoint 60.000
```

Header và `schemaVersion` vẫn giống nhau, nhưng vị trí logic thứ 60.001 không còn chắc chắn tương ứng với dữ liệu ban đầu. Do vậy, batch restartable cần **nguồn input bất biến**, hoặc phải dùng snapshot/immutable object version và kiểm tra revision trước khi resume.

Checksum SHA-256 của file là bằng chứng tốt để phát hiện thay đổi byte. Với file rất lớn, tính checksum nhiều lần có thể tốn I/O; có thể tính lúc nhận file, lưu metadata có nguồn tin cậy, dùng object version đã khóa và định kỳ xác minh theo chính sách. Không coi ETag của mọi object store là hash SHA-256; đặc biệt khi dùng multipart upload, ý nghĩa ETag có thể khác.

## 9. Khi schema không phù hợp: fail fast, skip hay quarantine?

Không phải mọi lỗi đều có cùng mức độ nghiêm trọng.

| Lỗi | Ví dụ | Phản ứng thường phù hợp |
|---|---|---|
| Version không được hỗ trợ | Manifest `schemaVersion=v5`, consumer chỉ hỗ trợ v1/v2 | **Từ chối toàn input** trước khi chạy writer; báo lỗi hợp đồng. |
| File thiếu header hoặc header sai với version | Metadata `v2`, file chỉ có cột v1 | Fail fast; không tự đoán v1 trừ khi có chính sách fallback chính thức. |
| Dữ liệu đầu vào thay đổi giữa restart | Checksum/revision không khớp | Dừng và điều tra; không tiếp tục checkpoint cũ. |
| Một bản ghi sai kiểu | `amount=ABC` trong file v2 hợp lệ về cấu trúc | Theo policy: fail, skip có giới hạn, hoặc lưu quarantine. |
| Một bản ghi thiếu trường bắt buộc | `currency` rỗng | Thường validate/quarantine hoặc fail khi vượt ngưỡng. |
| Giá trị mới chưa được business hỗ trợ | `currency=XYZ` | Reject/quarantine theo danh sách hợp lệ, không ngầm đổi sang default. |
| File có số record/record count sai manifest | Thiếu/trùng dữ liệu hoặc manifest sai | Báo lỗi đối soát, xác định có được publish hay không. |

Spring Batch hỗ trợ fault tolerance ở chunk step, ví dụ `.faultTolerant().skip(...)` cho các ngoại lệ đã được phân loại. Tuy nhiên, **không nên dùng skip policy để nuốt lỗi schema của toàn file**. Nếu tất cả record của `v3` đều bị parser v2 từ chối, job có thể ghi hàng triệu skip, tạo log lớn rồi hoàn thành sai. Schema compatibility phải được xác minh ở ranh giới trước khi áp dụng skip rule cho lỗi item cá biệt.

### 9.1. Quarantine và khả năng audit

Với policy cho phép bỏ qua bản ghi lỗi, nên lưu metadata tương ứng ở nơi được thiết kế cho dữ liệu bị từ chối:

```text
ingestion_id        : ingest-20261116-42
schema_version      : v2
source_revision     : rev-00042
record_number       : 187
error_code          : INVALID_AMOUNT
error_category      : DATA_VALIDATION
```

Không cần đưa toàn bộ payload có thông tin cá nhân lên log. Bảng/file quarantine cần có chính sách truy cập và retention phù hợp. Khi sử dụng listener để ghi quarantine, phải hiểu transaction và rollback; nếu ghi lỗi vào cùng transaction bị rollback, bản ghi quarantine có thể biến mất. Nếu ghi ngoài transaction, cần idempotency để tránh duplicate khi retry/restart.

### 9.2. Giới hạn tỷ lệ lỗi

Một số batch cho phép tối đa N record không hợp lệ, nhưng policy này chỉ nên áp dụng **sau khi biết cấu trúc file đúng version**. Ngoài số skip tuyệt đối, có thể cần tỷ lệ phần trăm lỗi hoặc ngưỡng theo loại lỗi, ví dụ `invalidCurrencyCount > 100` phải đánh dấu job thất bại. Đừng để một file hoàn toàn sai schema được chấp nhận chỉ vì `.skipLimit(Integer.MAX_VALUE)`.

## 10. Test schema version bằng JUnit

### 10.1. Unit test cho preflight

`OrderSchemaPreflight` dùng Java core, nên có thể test không cần Spring context hoặc `JobRepository`. Với JUnit Jupiter:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class OrderSchemaPreflightTest {

    @TempDir
    Path tempDir;

    private final OrderSchemaPreflight preflight = new OrderSchemaPreflight();

    @Test
    void acceptsV1Header() throws IOException {
        Path input = tempDir.resolve("orders-v1.csv");
        Files.writeString(input, """
                # schema-version: v1
                order_id,customer_id,amount
                ORD-1,CUS-1,1000
                """, StandardCharsets.UTF_8);

        OrderSchemaPreflight.Result result = preflight.inspect(input);

        assertEquals("v1", result.version());
        assertEquals(3, result.columns().size());
    }

    @Test
    void rejectsUnknownVersionBeforeProcessing() throws IOException {
        Path input = tempDir.resolve("orders-v9.csv");
        Files.writeString(input, """
                # schema-version: v9
                order_id,customer_id,amount,new_field
                ORD-1,CUS-1,1000,X
                """, StandardCharsets.UTF_8);

        assertThrows(IllegalArgumentException.class,
                () -> preflight.inspect(input));
    }

    @Test
    void rejectsHeaderMismatchEvenForKnownVersion() throws IOException {
        Path input = tempDir.resolve("bad-v2.csv");
        Files.writeString(input, """
                # schema-version: v2
                order_id,customer_id,amount
                ORD-1,CUS-1,1000
                """, StandardCharsets.UTF_8);

        assertThrows(IllegalArgumentException.class,
                () -> preflight.inspect(input));
    }
}
```

Các test này kiểm tra **chính sách version và header**. Chúng chưa kiểm tra mọi dòng, khả năng parsing quote/multiline hay độ chính xác của mapping. Bổ sung test ở mức reader cho mỗi version được hỗ trợ, bao gồm record hợp lệ, dữ liệu null, tiền tệ không hợp lệ và những ca biên của `BigDecimal`.

### 10.2. Integration test với Spring Batch

Một bài test tích hợp nên chạy `validateInputSchema -> importOrders` trên database test để xác minh:

1. File `v1` hợp lệ chạy được và được chuyển đổi thành VND đúng hợp đồng.
2. File `v2` hợp lệ giữ `currency` của đầu vào.
3. File có `v9` hoặc header v2 sai khiến **job thất bại trước khi writer ghi dữ liệu**.
4. File có schema hợp lệ nhưng một record sai kiểu được xử lý đúng skip/quarantine policy.
5. Kết quả cuối cùng trong database tương ứng với số item đã commit, không đơn thuần bằng số dòng được reader đọc.

Với Spring Batch 5.x, có thể sử dụng `@SpringBatchTest`, `@SpringBootTest`, `@ActiveProfiles("test")` và `JobLauncherTestUtils.launchJob(parameters)` để chạy toàn flow. Dùng datasource test cô lập và chuẩn bị input trong `@TempDir`. Nếu dùng file theo `JobParameters`, truyền đường dẫn từ `@TempDir` và tạo một identifying key rõ ràng cho mỗi test.

Ví dụ phần assertion chính:

```java
JobParameters params = new JobParametersBuilder()
        .addString("inputPath", inputFile.toString(), true)
        .addString("schemaVersion", "v2", true)
        .addString("batchId", "test-673-v2", true)
        .toJobParameters();

JobExecution execution = launcherTestUtils.launchJob(params);
assertEquals(BatchStatus.COMPLETED, execution.getStatus());

// Bổ sung assertion dữ liệu output thực tế qua JDBC/Repository.
```

Đây là **đoạn minh họa**, giả định đã có `inputFile`, `launcherTestUtils`, job bean, Batch `JobRepository` cùng datasource test và các import cần thiết. Với trường hợp unknown version, có thể kiểm tra `BatchStatus.FAILED` và bảng đích không chứa record mới; tránh chỉ kiểm tra exception message.

### 10.3. Restart test với schema giữ nguyên nhưng file thay đổi

Một lỗi khó phát hiện là file `v2` ban đầu thay đổi nội dung sau khi job commit vài chunk. Test phục hồi cần:

```text
1. Tạo file v2 có N records, xác định checksum/revision.
2. Chạy job, gây lỗi sau một số chunk đã commit.
3. Giữ JobRepository và checkpoint, không cleanup metadata.
4. Thay đổi nội dung file nhưng giữ header/version v2.
5. Thử restart với cùng identifying JobParameters.
6. Xác minh preflight/revision guard từ chối resume.
7. Khôi phục file/revision cũ rồi restart; kiểm tra output không trùng.
```

Đừng thay `schemaVersion` thành v3 để tạo instance mới rồi gọi đó là “restart”: đó là một lần ingest logic mới nếu identifying parameters đổi. Test restart thật cần cùng `JobInstance` và metadata được giữ lại giữa hai lần chạy.

## 11. Khi input là JSON, Avro, Parquet hoặc dữ liệu database

### 11.1. JSON và NDJSON

Với JSON, có thể đưa `schemaVersion` vào envelope hoặc metadata manifest. Batch reader sử dụng Jackson có thể deserialize về DTO theo version rồi map về canonical model. Một số thay đổi như thêm field có thể được chấp nhận nếu cấu hình deserializer cho phép unknown properties; nhưng **cho phép unknown field không giải quyết thay đổi ngữ nghĩa**.

Nếu dùng NDJSON, mỗi dòng thường là một JSON object. Cần quy định version ở manifest cho cả file hay từng record. Trộn nhiều version trong một file chỉ nên được hỗ trợ khi hợp đồng thật sự cho phép; khi đó parser phải chọn đúng mapper cho từng record và theo dõi số lượng lỗi theo version.

### 11.2. Avro, Protobuf và schema registry

Các định dạng có schema định nghĩa rõ field number/name, type, default và quy tắc resolution. Khi có schema registry, nên dùng cơ chế kiểm tra compatibility của registry cùng với integration test của consumer thực tế. Quy tắc tương thích phụ thuộc định dạng và policy (BACKWARD, FORWARD, FULL, transitive...), nên không suy luận từ tên policy mà bỏ qua việc test.

### 11.3. Parquet

Parquet lưu schema trong metadata file. Pipeline có thể đọc schema footer để kiểm tra cột và kiểu trước khi scan toàn bộ dữ liệu. Tuy nhiên version contract nghiệp vụ có thể chứa những quy tắc **không thể biểu diễn chỉ bằng Parquet physical schema** như đơn vị tiền hoặc business timezone; vẫn nên có contract/version tường minh.

### 11.4. Staging database

Nếu input nằm trong một bảng staging, có thể lưu `schema_version`, `source_revision` và `ingestion_id` ở bảng manifest/batch. Tránh thay đổi trực tiếp schema staging trong khi một job đang đọc. Dùng migration hoặc view/adapter theo phiên bản, và gắn mỗi đợt ingest với một snapshot dữ liệu đủ ổn định cho restart.

## 12. Thiết kế quan sát và đối soát schema version

Một pipeline dữ liệu lớn nên có audit record hoặc metadata ingestion theo lô:

| Trường | Mục đích |
|---|---|
| `ingestionId` | Khóa kỹ thuật của đợt nhận dữ liệu. |
| `dataset` | Loại dữ liệu: `orders`, `customers`... |
| `schemaVersion` | Phiên bản đã được xác nhận, không chỉ giá trị bên gửi khai báo. |
| `inputRevision`/checksum | Định danh nội dung vật lý đã xử lý. |
| `jobInstanceId`, `jobExecutionId` | Tương quan với metadata Spring Batch. |
| `receivedCount`, `validCount`, `rejectedCount`, `writtenCount` | Đối soát số lượng theo định nghĩa nghiệp vụ. |
| `status`, `errorCode` | Kết quả nhận và kiểm tra input. |
| `receivedAt`, `finishedAt` | Thời gian tiếp nhận và kết thúc. |

Log theo đợt nên có tên sự kiện thống nhất:

```text
batch.input.schema.accepted dataset=orders schemaVersion=v2 ingestionId=ing-42
batch.input.schema.rejected dataset=orders schemaVersion=v9 reason=UNSUPPORTED_VERSION ingestionId=ing-43
batch.input.completed dataset=orders schemaVersion=v2 accepted=9990 rejected=10
```

Đây là log minh họa; **không in toàn bộ file, payload hay `JobParameters`** vì có thể chứa thông tin nhạy cảm và gây tăng log không kiểm soát. Với metrics, có thể nhóm theo dataset và **số phiên bản được quản lý hữu hạn**; không thêm các ID mỗi lần chạy làm metric tag vì tạo cardinality lớn. Job execution ID phù hợp hơn với log/trace.

Để kiểm tra tính đầy đủ dữ liệu, so sánh số records trong manifest (nếu đáng tin cậy) với số bản ghi thực tế và số kết quả đã commit. `StepExecution.getReadCount()`/`getWriteCount()` có ngữ nghĩa riêng trong chunk processing; chúng không luôn tương đương số dòng file hay số row SQL đổi trạng thái. Cần tính đến filter, skip, retry, rollback và cách writer hoạt động.

## 13. Thay đổi schema an toàn giữa hai hệ thống

Một quy trình thay đổi hợp đồng nên có những bước sau:

1. **Công bố phiên bản mới:** xác định chính xác các trường thay đổi, kiểu, default, timezone, enum và ý nghĩa nghiệp vụ.
2. **Phân loại breaking/non-breaking:** dựa trên các reader thực tế, không chỉ bảng field names.
3. **Viết mapping về canonical model:** parser v1/v2 cùng sinh mô hình đầu ra đã được chuẩn hóa rõ quy tắc.
4. **Thêm contract tests:** giữ fixture đại diện của phiên bản cũ và mới; thử missing/unknown fields, invalid values, header khác thứ tự.
5. **Triển khai consumer hỗ trợ version mới trước khi producer phát dữ liệu mới** nếu chiến lược rollout yêu cầu tương thích backward.
6. **Cho phép giai đoạn chuyển tiếp:** log/metric số input của từng version, đưa ra kế hoạch loại bỏ version cũ.
7. **Cố định input revision khi nhận file:** bảo vệ restart, đối soát và khả năng tái hiện kết quả.
8. **Gỡ hỗ trợ version cũ có kiểm soát:** sau khi xác nhận nguồn không còn gửi file cũ và các trường hợp backfill đã có đường xử lý.

Khi có nhiều producer, có thể dùng schema registry hoặc hợp đồng versioned artifacts thay vì chia sẻ một file Excel mô tả field mà không có kiểm tra tự động. Mỗi producer cần chịu trách nhiệm khai báo version trung thực, còn consumer vẫn phải validate file thực nhận.

### 13.1. Không ghép version triển khai ứng dụng với version input

Ví dụ `order-batch-app 2.3.1` có thể đọc cả `input schema v1` và `v2`. Đổi patch version ứng dụng không có nghĩa schema input phải tăng, và cùng một schema input có thể được hỗ trợ bởi nhiều phiên bản application. Nên quản lý hai khái niệm độc lập:

```text
Application release: 2.3.1
Supported input schemas: orders/v1, orders/v2
Canonical model version: OrderNormalized/1
Database migration: V12
```

Chỉ gắn chúng với nhau qua bảng compatibility chính thức trong release notes/contract tests. Điều này đặc biệt quan trọng khi chạy lại một input cũ bằng bản application mới sau nhiều tháng.

## 14. Những lỗi phổ biến khi quản lý schema version

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| File v2 bị reader v1 từ chối | Reader strict mong số cột/field cũ | Nhận diện version trước, chọn parser tương ứng. |
| Job thành công nhưng số tiền sai | Thay đổi đơn vị hoặc nghĩa của field mà không đổi contract | Version hóa cả ngữ nghĩa, bổ sung conversion test. |
| Unknown version vẫn được nhập | Có parser mặc định hoặc `default` branch nuốt lỗi | Fail fast trên version chưa hỗ trợ. |
| Header báo v2 nhưng nội dung là v1 | Producer/manifest sai, file bị ghi nhầm | Đối chiếu header/manifest và kiểm tra kiểu dữ liệu thực tế. |
| Restart đọc lệch item | File bị ghi đè sau checkpoint | Dùng immutable input revision/checksum và fail nếu thay đổi. |
| Đọc CSV sai khi có dấu phẩy trong dữ liệu | Dùng `String.split(",")` thay cho parser hỗ trợ quote/escape | Dùng tokenizer/parser CSV theo hợp đồng. |
| Reader ghi trùng checkpoint | Hai reader dùng cùng `name` trong một execution context | Đặt tên `ItemStream` duy nhất và ổn định cho từng stream. |
| Bỏ sót lỗi ở cuối file | Chỉ kiểm tra hai dòng đầu rồi coi toàn input đã hợp lệ | Phân biệt preflight schema với validation từng record và đối soát cuối. |
| Một file sai schema tạo hàng triệu skip | Lỗi version bị phân loại nhầm thành item-level error | Reject toàn file trước processing, không dùng unlimited skip. |
| Version đúng nhưng enum mới gây crash | Business enum chưa được nâng cấp | Version hóa tập giá trị/unknown policy và bổ sung contract test. |
| Log đầy payload khi dữ liệu lỗi | Listener in item/JSON/params nguyên vẹn | Chỉ log error code, record number, ingestion ID; dùng quarantine bảo mật. |
| Việc nâng application làm backfill cũ lỗi | Gỡ reader v1 hoặc thay semantics không giữ compatibility | Giữ adapter legacy/test fixture trong thời gian hỗ trợ, hoặc có migration input. |
| Cùng object key nhưng dữ liệu khác | Producer ghi đè file, object metadata không được pin | Lưu object version/digest thật, khóa nguồn trong suốt vòng đời job. |
| H2 test qua nhưng production lỗi | Data type/dialect khác hoặc parser/locale khác | Test thêm với database/format thật, cố định locale/timezone. |

## 15. Bài tập thực hành

### Bài 1 — Hỗ trợ đồng thời v1 và v2

Tạo hai file CSV theo ví dụ ở mục 1. Viết `OrderSchemaPreflight.inspect(...)`, tạo `FlatFileItemReader<NormalizedOrder>` tương ứng và xác minh cả hai input được ánh xạ đúng. Kiểm tra rằng `v1` dùng đơn vị `VND` **chỉ vì hợp đồng v1 quy định như vậy**, còn `v2` lấy đơn vị từ file.

### Bài 2 — Reject unknown version trước khi ghi database

Tạo một file có `# schema-version: v9`, chạy flow gồm `validateInputSchema -> importOrders` bằng `@SpringBatchTest`. Kiểm tra job ở trạng thái thất bại, step import chưa ghi dữ liệu, và metadata lỗi có code dễ đối soát. Thử trường hợp header `v2` nhưng thiếu cột `currency`.

### Bài 3 — Dữ liệu xấu trong file đúng schema

Giữ version `v2`, thêm record `amount=ABC` hoặc `currency` không hợp lệ. Phân loại lỗi parse và lỗi nghiệp vụ; thiết kế ngưỡng skip/quarantine. Đảm bảo output không chứa bản ghi lỗi và tổng số accepted/rejected khớp số record đầu vào thực tế.

### Bài 4 — File thay đổi giữa hai lần restart

Chạy job v2 có `ExecutionContext` checkpoint sau một số chunk, gây lỗi, thay đổi thứ tự record trong cùng path rồi thử restart. Bổ sung checksum hoặc immutable revision để phát hiện thay đổi và dừng trước khi đọc tiếp. Khôi phục input đúng revision và kiểm tra kết quả cuối không trùng.

### Bài 5 — Thiết kế v3 không phá quy tắc nghiệp vụ

Thiết kế input `v3` có `net_amount`, `tax_amount` và `currency`. Viết mapping sang `NormalizedOrder` với giả định nghiệp vụ rõ ràng về thuế và tổng tiền; bổ sung test cho null, precision, rounding và currency lạ. Đánh giá xem `v3` backward/forward compatible với consumer hiện tại không, rồi đưa ra kế hoạch triển khai producer/consumer.

## 16. Nguyên tắc triển khai trong hệ thống batch thực tế

Một pipeline có schema input được quản lý tốt thường đáp ứng:

1. **Version được công bố tường minh** ở file header, manifest, metadata object hoặc registry.
2. **Mỗi version có hợp đồng xác định** về cấu trúc và ngữ nghĩa, có fixture và test để bảo vệ.
3. **Consumer chỉ nhận những version đã được hỗ trợ**, từ chối unknown và mismatch trước khi xử lý dữ liệu.
4. **Mọi version được chuẩn hóa tại biên input** trước khi đi vào logic xử lý chung.
5. **Input và version được pin cho toàn bộ JobInstance**, đặc biệt trong restart và backfill.
6. **Lỗi hợp đồng được phân biệt với lỗi từng record**, có chính sách fail, skip hoặc quarantine rõ ràng.
7. **Dữ liệu đầu ra được đối soát** theo số lượng, khóa nghiệp vụ và trạng thái đã commit; không dựa vào một log `COMPLETED` duy nhất.
8. **Version cũ được loại bỏ theo kế hoạch**, có monitoring cho nguồn vẫn phát dữ liệu cũ và kiểm thử tương thích.
9. **Schema input, schema database và version ứng dụng được theo dõi riêng**, tránh nhầm lẫn khi vận hành và nâng cấp.

## 17. Tài liệu tham khảo

- [Spring Batch Reference — Flat Files](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-reader.html): `FlatFileItemReader`, `LineMapper`, tokenizer, strict parsing và cấu hình reader.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): checkpoint với `ExecutionContext`, `open/update/close` và khả năng restart.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): hành vi restart và xử lý trạng thái step.
- [Spring Batch Reference — Job Parameters](https://docs.spring.io/spring-batch/reference/job/running.html): truyền tham số và định danh một job instance.
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): phân biệt xử lý lỗi item với lỗi hợp đồng đầu vào.
- [Apache Avro Specification](https://avro.apache.org/docs/current/specification/): quy tắc writer/reader schema và schema resolution cho dữ liệu Avro.
- [Protocol Buffers — Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating): nguyên tắc thay đổi message schema tương thích trong Protobuf.

