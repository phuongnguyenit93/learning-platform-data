# FixedLengthTokenizer

Trong Spring Batch, `FixedLengthTokenizer` dùng để tách một dòng văn bản có các trường nằm ở những vị trí cố định. Khác với file phân tách bằng dấu phẩy hoặc tab, file fixed-width không cần ký tự delimiter giữa các cột. Vị trí bắt đầu và kết thúc của từng trường được mô tả bằng các `Range`.

Tokenizer chuyển một dòng thành `FieldSet`. Sau đó, `FieldSetMapper` chuyển các giá trị đã tách thành object nghiệp vụ. Thành phần này thường được dùng cùng `FlatFileItemReader` và `DefaultLineMapper` để đọc các file legacy, file trao đổi với hệ thống ngân hàng, mainframe hoặc hệ thống có định dạng bản ghi theo độ rộng cố định.

## 1. File fixed-width là gì?

File fixed-width (fixed-length record) là file mà mỗi trường chiếm một khoảng vị trí đã được quy định trước trong dòng dữ liệu. Ví dụ, một bản ghi nhân viên có độ dài 60 ký tự:

| Trường | Vị trí bắt đầu | Vị trí kết thúc | Độ dài |
|---|---:|---:|---:|
| `employeeId` | 1 | 8 | 8 |
| `lastName` | 9 | 28 | 20 |
| `firstName` | 29 | 43 | 15 |
| `hireDate` | 44 | 51 | 8 |
| `salary` | 52 | 60 | 9 |

Minh họa cách chia một dòng:

```text
12345678NGUYEN VAN A        ANH            20261115000012500
|------|--------------------|---------------|--------|---------|
   ID          Last name        First name     Date     Salary
  1-8             9-28             29-43       44-51    52-60
```

Trong ví dụ, không có dấu phẩy hoặc dấu tab để phân cách. Reader phải biết chính xác vị trí của từng trường. Nếu cấu hình sai một vị trí, phần còn lại của bản ghi có thể bị tách sai dù dòng vẫn có vẻ hợp lệ.

## 2. Vai trò của FixedLengthTokenizer

`FixedLengthTokenizer` triển khai `LineTokenizer`. Nó nhận một dòng `String`, cắt dòng theo các range đã cấu hình và trả về `FieldSet` chứa các trường theo thứ tự tương ứng.

Quy trình xử lý thường có dạng:

```text
FlatFileItemReader
       |
       | đọc một dòng
       v
DefaultLineMapper
       |
       v
FixedLengthTokenizer
       |
       | cắt theo Range
       v
FieldSet
       |
       v
FieldSetMapper
       |
       | chuyển kiểu và ánh xạ
       v
Domain object
```

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
|---|---|
| `FlatFileItemReader` | Đọc từng dòng từ resource, quản lý encoding, header, comment và trạng thái reader. |
| `DefaultLineMapper` | Kết hợp tokenizer với mapper để chuyển một dòng thành object. |
| `FixedLengthTokenizer` | Tách dòng thành các trường theo vị trí cố định. |
| `Range` | Mô tả vị trí bắt đầu và kết thúc của một trường. |
| `FieldSet` | Cung cấp API đọc giá trị theo tên hoặc chỉ số và chuyển đổi kiểu. |
| `FieldSetMapper` | Chuyển `FieldSet` thành object nghiệp vụ. |

Tokenizer chỉ chịu trách nhiệm tách trường. Nó không tự hiểu `employeeId` có tồn tại trong hệ thống, ngày có hợp lệ về nghiệp vụ hay lương có nằm trong giới hạn cho phép. Các kiểm tra đó thuộc mapper, processor hoặc validator.

## 3. Khai báo Range

`Range` biểu diễn vị trí của một trường trong dòng. Các vị trí của `Range` là 1-based và điểm cuối là inclusive.

Ví dụ:

```java
new Range(1, 8)   // ký tự từ vị trí 1 đến 8
new Range(9, 28)  // ký tự từ vị trí 9 đến 28
new Range(29, 43) // ký tự từ vị trí 29 đến 43
```

Độ dài trường được tính bằng:

\[
\text{length} = \text{end} - \text{start} + 1
\]

Vì vậy `new Range(1, 8)` có độ dài 8, không phải 7. Đây là lỗi cấu hình thường gặp khi chuyển tài liệu vị trí từ định dạng 1-based sang phép tính index 0-based của Java.

`Range` cũng có thể được khai báo với điểm bắt đầu mà không chỉ định điểm kết thúc, ví dụ `new Range(21)`, để biểu diễn trường kéo dài từ vị trí 21 đến cuối dòng. Chỉ nên dùng range mở khi định dạng nguồn thực sự quy định trường cuối có độ dài thay đổi.

## 4. Cấu hình FixedLengthTokenizer cơ bản

Một tokenizer cơ bản cần hai cấu hình chính:

- `setColumns(...)`: danh sách các range theo thứ tự trường xuất hiện trong dòng.
- `setNames(...)`: tên tương ứng của các trường trong `FieldSet`.

Ví dụ:

```java
FixedLengthTokenizer tokenizer = new FixedLengthTokenizer();
tokenizer.setNames("employeeId", "lastName", "firstName", "hireDate", "salary");
tokenizer.setColumns(
        new Range(1, 8),
        new Range(9, 28),
        new Range(29, 43),
        new Range(44, 51),
        new Range(52, 60));
tokenizer.setStrict(true);
```

Thứ tự trong `setNames` phải tương ứng với thứ tự trong `setColumns`. Trường đầu tiên được cắt từ range đầu tiên và gắn với tên đầu tiên, trường thứ hai gắn với tên thứ hai, v.v.

Khi định nghĩa range, hãy kiểm tra:

- Số tên trường bằng số range.
- Các vị trí bắt đầu và kết thúc đúng theo đặc tả file.
- Range được sắp xếp theo thứ tự xuất hiện trong bản ghi.
- Các range không vô tình chồng lấn.
- Không bỏ sót vị trí cần đọc.
- Khoảng bị bỏ qua chỉ là padding hoặc trường không cần dùng theo đặc tả.

Nếu file có một đoạn reserved/padding không cần ánh xạ, có thể không khai báo range cho đoạn đó, miễn là vị trí của các trường sau vẫn được tính theo offset gốc của file.

## 5. Ví dụ hoàn chỉnh với FlatFileItemReader

Giả sử file nhân viên có các trường `employeeId`, `lastName`, `firstName`, `hireDate` và `salary`, với độ dài lần lượt là 8, 20, 15, 8 và 9 ký tự.

Định nghĩa domain object:

```java
public record Employee(
        String employeeId,
        String lastName,
        String firstName,
        LocalDate hireDate,
        BigDecimal salary) {
}
```

Khai báo `LineMapper`:

```java
@Bean
LineMapper<Employee> employeeLineMapper() {
    FixedLengthTokenizer tokenizer = new FixedLengthTokenizer();
    tokenizer.setNames(
            "employeeId", "lastName", "firstName", "hireDate", "salary");
    tokenizer.setColumns(
            new Range(1, 8),
            new Range(9, 28),
            new Range(29, 43),
            new Range(44, 51),
            new Range(52, 60));
    tokenizer.setStrict(true);

    DefaultLineMapper<Employee> lineMapper = new DefaultLineMapper<>();
    lineMapper.setLineTokenizer(tokenizer);
    lineMapper.setFieldSetMapper(fieldSet -> new Employee(
            fieldSet.readString("employeeId").trim(),
            fieldSet.readString("lastName").trim(),
            fieldSet.readString("firstName").trim(),
            LocalDate.parse(
                    fieldSet.readString("hireDate").trim(),
                    DateTimeFormatter.BASIC_ISO_DATE),
            new BigDecimal(fieldSet.readString("salary").trim())));
    return lineMapper;
}
```

Khai báo reader:

```java
@Bean
@StepScope
FlatFileItemReader<Employee> employeeReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        LineMapper<Employee> employeeLineMapper) {

    return new FlatFileItemReaderBuilder<Employee>()
            .name("employeeReader")
            .resource(new FileSystemResource(inputFile))
            .encoding("UTF-8")
            .linesToSkip(1)
            .lineMapper(employeeLineMapper)
            .saveState(true)
            .build();
}
```

Reader bỏ qua dòng đầu tiên nếu file có header. Nếu file không có header, bỏ `.linesToSkip(1)`. `@StepScope` cho phép nhận `inputFile` từ JobParameters tại thời điểm step bắt đầu.

Ví dụ trên giả định lương được lưu bằng chữ số và ngày theo `yyyyMMdd`. Nếu file có dấu âm, dấu thập phân, dấu phân nhóm hoặc quy ước ngày khác, mapper phải parse theo đúng format của nguồn.

## 6. FixedLengthTokenizer và FieldSetMapper

Tokenizer chỉ cắt chuỗi. Việc chuyển từ chuỗi sang kiểu dữ liệu và tạo domain object thuộc `FieldSetMapper`.

Ví dụ tách mapper thành một class riêng:

```java
public class EmployeeFieldSetMapper implements FieldSetMapper<Employee> {

    private static final DateTimeFormatter DATE_FORMAT =
            DateTimeFormatter.BASIC_ISO_DATE;

    @Override
    public Employee mapFieldSet(FieldSet fieldSet) {
        String employeeId = fieldSet.readString("employeeId").trim();
        String lastName = fieldSet.readString("lastName").trim();
        String firstName = fieldSet.readString("firstName").trim();

        LocalDate hireDate = LocalDate.parse(
                fieldSet.readString("hireDate").trim(), DATE_FORMAT);
        BigDecimal salary = new BigDecimal(
                fieldSet.readString("salary").trim());

        return new Employee(employeeId, lastName, firstName, hireDate, salary);
    }
}
```

Sau đó cấu hình:

```java
lineMapper.setFieldSetMapper(new EmployeeFieldSetMapper());
```

Tách mapper riêng có lợi khi quy tắc chuyển đổi phức tạp, cần kiểm thử độc lập hoặc được dùng ở nhiều reader. Với mapping đơn giản, lambda có thể ngắn gọn hơn.

### Xử lý khoảng trắng

Các trường fixed-width thường được đệm bằng dấu cách. Ví dụ trường họ tên có thể chứa `"NGUYEN VAN A        "`. Hãy xác định rõ có cần giữ khoảng trắng đầu/cuối hay không.

- Dùng `.trim()` nếu khoảng trắng chỉ là padding và không có ý nghĩa dữ liệu.
- Dùng `strip()` khi muốn xử lý thêm một số ký tự whitespace Unicode theo Java hiện đại.
- Không trim tự động nếu khoảng trắng là một phần hợp lệ của dữ liệu nguồn.
- Với trường mã có padding bằng số 0, không xóa số 0 đầu nếu chúng là một phần của định danh.

Không nên dựa vào tokenizer để chuẩn hóa mọi trường. Hãy thực hiện chuẩn hóa trong mapper để quy tắc rõ ràng và có thể kiểm thử.

## 7. Strict mode và độ dài bản ghi

`FixedLengthTokenizer` có thuộc tính strict. Khi bật strict, tokenizer kiểm tra độ dài bản ghi theo các range đã khai báo và báo lỗi định dạng nếu dòng không đáp ứng độ dài mong đợi.

```java
tokenizer.setStrict(true);
```

Ví dụ, nếu range cuối kết thúc ở vị trí 60, một bản ghi ngắn hơn mức cần thiết không thể cung cấp đủ dữ liệu cho các trường được định nghĩa. `IncorrectLineLengthException` là loại lỗi có thể gặp khi chiều dài dòng không phù hợp với cấu hình strict.

Khi `strict` tắt:

```java
tokenizer.setStrict(false);
```

Tokenizer nới lỏng việc kiểm tra độ dài. Các trường ở cuối dòng có thể ngắn hoặc không có đủ ký tự theo định dạng mong đợi, tùy range và implementation của phiên bản đang dùng. Vì vậy, mapper cần kiểm tra dữ liệu thiếu trước khi parse hoặc ghi database.

Nên giữ strict mode cho file có đặc tả độ dài rõ ràng. Chỉ tắt strict khi nguồn thực sự cho phép record ngắn hoặc biến thể độ dài và ứng dụng có quy tắc xử lý phần thiếu.

### Phân biệt hai thuộc tính strict

Có hai cấu hình dễ bị nhầm:

| Cấu hình | Ý nghĩa |
|---|---|
| `FixedLengthTokenizer.setStrict(...)` | Kiểm tra độ dài dòng so với các range của tokenizer. |
| `FlatFileItemReaderBuilder.strict(...)` | Kiểm tra resource đầu vào có tồn tại/đọc được theo quy tắc của reader hay không. |

Ví dụ:

```java
tokenizer.setStrict(true); // Kiểm tra cấu trúc fixed-width của từng dòng.

return new FlatFileItemReaderBuilder<Employee>()
        .name("employeeReader")
        .resource(resource)
        .strict(true) // Kiểm tra resource theo strict mode của reader.
        .lineMapper(lineMapper)
        .build();
```

Hai thuộc tính kiểm tra hai vấn đề khác nhau. Một resource tồn tại không có nghĩa mọi dòng đều có độ dài hợp lệ; ngược lại, tokenizer được cấu hình đúng cũng không thể đọc nếu file không tồn tại.

## 8. Range có khoảng trống và trường không sử dụng

Một bản ghi có thể chứa trường reserved hoặc padding mà ứng dụng không cần ánh xạ. Ví dụ:

| Trường | Vị trí |
|---|---:|
| `accountId` | 1-10 |
| reserved | 11-15 |
| `accountName` | 16-40 |
| `status` | 41-41 |

Có thể chỉ khai báo các range cần đọc:

```java
tokenizer.setNames("accountId", "accountName", "status");
tokenizer.setColumns(
        new Range(1, 10),
        new Range(16, 40),
        new Range(41, 41));
```

Tokenizer lấy đúng các vị trí được chỉ định. Khoảng reserved 11-15 không được đưa vào FieldSet. Các vị trí của trường sau vẫn phải tính theo vị trí gốc của bản ghi, không được dồn lại như thể reserved không tồn tại.

Nếu có nhiều khoảng bỏ qua, hãy ghi chú rõ theo đặc tả file. Tránh thay đổi range chỉ để làm code trông liên tục vì điều đó sẽ dịch offset của các trường sau.

## 9. Range mở cho trường cuối

Nếu trường cuối chiếm toàn bộ phần còn lại của dòng, có thể dùng range chỉ có vị trí bắt đầu:

```java
tokenizer.setNames("recordType", "recordId", "description");
tokenizer.setColumns(
        new Range(1, 2),
        new Range(3, 12),
        new Range(13));
```

Ở đây `description` bắt đầu tại vị trí 13 và kéo dài đến cuối dòng. Range mở hữu ích khi phần mô tả có độ dài thay đổi nhưng các trường trước vẫn có vị trí cố định.

Khi dùng range mở, cần kiểm tra record tối thiểu để bảo đảm trường cuối không bị rỗng ngoài ý muốn. Strict validation cũng cần được kiểm tra theo semantics của range mở và phiên bản Spring Batch cụ thể.

## 10. Encoding và ý nghĩa của độ rộng

Đây là điểm quan trọng khi đọc file fixed-width từ hệ thống legacy. `FixedLengthTokenizer` làm việc trên dòng `String` đã được reader giải mã, sau đó cắt theo vị trí ký tự của chuỗi Java. Nó không cắt trực tiếp theo byte của file.

Nếu đặc tả nguồn định nghĩa độ rộng theo ký tự, điều này thường phù hợp. Nhưng nếu đặc tả định nghĩa độ rộng theo byte, nhất là với encoding nhiều byte, vị trí byte có thể khác vị trí ký tự sau giải mã.

Ví dụ:

- ASCII hoặc một số encoding single-byte: một ký tự thường tương ứng một byte.
- UTF-8: ký tự có thể chiếm nhiều byte.
- Một số encoding legacy như EBCDIC: cần chọn đúng charset khi đọc.

Hãy cấu hình `.encoding(...)` theo đúng charset của file. Nếu file được định nghĩa fixed-width theo byte, cần xác minh encoding và chiến lược giải mã trước khi dùng tokenizer theo vị trí ký tự. Có thể phải đọc/giải mã theo byte boundary hoặc chuyển file sang định dạng chuẩn trước khi tokenizing.

Với Unicode, Java `String` dùng UTF-16; một ký tự ngoài Basic Multilingual Plane có thể chiếm hai code unit. Nếu đặc tả đếm Unicode code point hoặc byte, không thể mặc định index của `String.substring` trùng với vị trí theo đặc tả. Cần kiểm thử bằng dữ liệu thực tế có ký tự đa byte/ngoài BMP nếu nguồn cho phép.

## 11. Dấu âm, số thập phân và định dạng ngày

Tokenizer trả các trường dưới dạng text. Các quy ước như dấu âm, dấu thập phân, decimal implied, dấu phân nhóm hoặc ngày tháng phải được xử lý ở mapper.

Ví dụ file có số tiền dạng 9 ký tự, trong đó hai chữ số cuối là phần thập phân ngầm định:

```text
000012345
```

Nếu đặc tả quy định giá trị là 123.45, mapper phải chuyển đổi theo quy tắc đó:

```java
String raw = fieldSet.readString("amount").trim();
BigDecimal amount = new BigDecimal(raw).movePointLeft(2);
```

Nếu file dùng dấu `-` ở đầu hoặc cuối trường, hãy parse theo format riêng và kiểm tra trường rỗng. Không dùng `new BigDecimal(...)` trực tiếp nếu nguồn có ký tự phân nhóm hoặc format không chuẩn.

Với ngày `yyyyMMdd`, có thể dùng:

```java
LocalDate date = LocalDate.parse(
        fieldSet.readString("hireDate").trim(),
        DateTimeFormatter.BASIC_ISO_DATE);
```

Nếu ngày sai định dạng, mapper có thể phát sinh exception. Trong chunk step, ứng dụng có thể cấu hình skip cho lỗi dữ liệu cụ thể nếu nghiệp vụ cho phép; lỗi cấu hình hoặc lỗi toàn file không nên bị skip tùy tiện.

## 12. Xử lý dòng header, comment và dòng trống

`FixedLengthTokenizer` chỉ xử lý dòng được chuyển tới nó. Việc bỏ header, comment hoặc dòng trống thuộc cấu hình của `FlatFileItemReader`.

Ví dụ:

```java
return new FlatFileItemReaderBuilder<Employee>()
        .name("employeeReader")
        .resource(resource)
        .linesToSkip(1)
        .comments("#")
        .lineMapper(lineMapper)
        .build();
```

- `linesToSkip(1)` bỏ dòng đầu tiên, thường dùng cho header.
- `comments("#")` đánh dấu tiền tố comment theo cấu hình reader.
- Dòng trống cần được xử lý theo yêu cầu file và cấu hình reader/mapper phù hợp.

Không nên dùng range để cố bỏ header hoặc comment. Hãy xử lý chúng ở reader để tokenizer chỉ nhận các record nghiệp vụ.

## 13. Kết hợp FixedLengthTokenizer với BeanWrapperFieldSetMapper

Nếu tên field trong `FieldSet` tương ứng với property của Java bean, có thể dùng `BeanWrapperFieldSetMapper` để tự động bind.

Ví dụ:

```java
@Bean
FieldSetMapper<EmployeeInput> employeeFieldSetMapper() {
    BeanWrapperFieldSetMapper<EmployeeInput> mapper =
            new BeanWrapperFieldSetMapper<>();
    mapper.setTargetType(EmployeeInput.class);
    return mapper;
}
```

Tokenizer cần đặt tên trường trùng với property có thể ghi của target object:

```java
tokenizer.setNames("employeeId", "lastName", "firstName", "hireDate", "salary");
```

Bean cần có cấu trúc phù hợp với cơ chế property binding, thường là constructor mặc định và setter cho các property hoặc một cấu hình mapper tương thích. Conversion service có thể được cấu hình nếu cần chuyển String sang `LocalDate`, `BigDecimal` hoặc enum theo format riêng.

Nếu target là Java record hoặc cần mapping phức tạp, một `FieldSetMapper` tự viết thường dễ kiểm soát hơn. Đừng giả định BeanWrapper tự hiểu mọi format ngày/số đặc thù của file.

## 14. Kiểm thử tokenizer độc lập

Có thể kiểm thử `FixedLengthTokenizer` mà không cần tạo Job hoặc database. Test trực tiếp dòng mẫu và xác nhận từng field:

```java
class EmployeeTokenizerTest {

    private FixedLengthTokenizer createTokenizer() {
        FixedLengthTokenizer tokenizer = new FixedLengthTokenizer();
        tokenizer.setNames(
                "employeeId", "lastName", "firstName", "hireDate", "salary");
        tokenizer.setColumns(
                new Range(1, 8),
                new Range(9, 28),
                new Range(29, 43),
                new Range(44, 51),
                new Range(52, 60));
        tokenizer.setStrict(true);
        return tokenizer;
    }

    @Test
    void extractsFieldsByPosition() {
        String line = "12345678NGUYEN VAN A        ANH            20261115000012500";

        FieldSet fields = createTokenizer().tokenize(line);

        assertThat(fields.readString("employeeId")).isEqualTo("12345678");
        assertThat(fields.readString("lastName").trim()).isEqualTo("NGUYEN VAN A");
        assertThat(fields.readString("firstName").trim()).isEqualTo("ANH");
        assertThat(fields.readString("hireDate")).isEqualTo("20261115");
        assertThat(fields.readString("salary")).isEqualTo("000012500");
    }
}
```

Trong test thực tế, cần bảo đảm dòng mẫu có đúng số ký tự theo đặc tả. Có thể tạo chuỗi từ các trường được padding để tránh đếm dấu cách bằng mắt.

## 15. Kiểm thử độ dài không hợp lệ

Với strict mode, cần test dòng ngắn hơn hoặc dài hơn cấu trúc được khai báo để xác nhận tokenizer từ chối record không hợp lệ theo cấu hình.

Ví dụ kiểm thử dòng quá ngắn:

```java
@Test
void rejectsLineShorterThanConfiguredRanges() {
    FixedLengthTokenizer tokenizer = createTokenizer();

    assertThatThrownBy(() -> tokenizer.tokenize("12345678SHORT"))
            .isInstanceOf(IncorrectLineLengthException.class);
}
```

Ngoài ra nên kiểm thử:

- Dòng đúng độ dài.
- Dòng ngắn hơn range cuối.
- Dòng dài hơn đặc tả nếu format yêu cầu độ dài chính xác.
- Trường cuối dùng range mở.
- Trường chứa toàn dấu cách.
- Trường chứa ký tự có dấu hoặc ký tự nhiều byte theo encoding nguồn.
- Giá trị số/ngày không hợp lệ sau khi tokenizer đã cắt đúng vị trí.

Với `strict=false`, test phải xác định rõ ứng dụng mong đợi gì khi thiếu ký tự. Không nên tắt strict mà không có test cho record ngắn.

## 16. Kiểm thử FieldSetMapper riêng

Tokenizer và mapper nên được kiểm thử riêng để xác định lỗi thuộc khâu nào.

Ví dụ test mapper:

```java
@Test
void mapsFieldSetToEmployee() {
    DefaultFieldSet fieldSet = new DefaultFieldSet(
            new String[]{
                    "12345678",
                    "NGUYEN VAN A        ",
                    "ANH            ",
                    "20261115",
                    "000012500"
            },
            new String[]{
                    "employeeId", "lastName", "firstName", "hireDate", "salary"
            });

    Employee employee = new EmployeeFieldSetMapper().mapFieldSet(fieldSet);

    assertThat(employee.employeeId()).isEqualTo("12345678");
    assertThat(employee.lastName()).isEqualTo("NGUYEN VAN A");
    assertThat(employee.hireDate()).isEqualTo(LocalDate.of(2026, 11, 15));
    assertThat(employee.salary()).isEqualByComparingTo("12500");
}
```

Test mapper cần bao gồm trường rỗng, ngày sai format, số âm, decimal implied và padding. Nếu mapper chịu trách nhiệm validate dữ liệu, hãy kiểm tra exception cụ thể để step có thể áp dụng skip policy đúng cách.

## 17. Kiểm thử tích hợp FlatFileItemReader

Tokenizer test không xác nhận reader mở file, áp dụng encoding, bỏ header và khôi phục checkpoint. Với những yêu cầu đó, cần integration test cho `FlatFileItemReader`.

Test có thể dùng file trong `src/test/resources`, tạo reader với `Resource` test và đọc lần lượt các item. Nên kiểm tra:

- File mở được và encoding đúng.
- Header được bỏ qua theo cấu hình.
- Dòng comment được xử lý đúng.
- Mỗi dòng được chuyển thành object với giá trị đúng.
- Dòng lỗi phát sinh exception mong đợi.
- Reader đóng resource sau khi test.
- `saveState` và checkpoint hoạt động nếu job cần restart.

Khi test restart, file nguồn phải giữ nguyên giữa lần chạy đầu và lần restart. Nếu nội dung file thay đổi nhưng tên/đường dẫn không đổi, checkpoint có thể trỏ đến dòng khác với dữ liệu ban đầu.

## 18. FixedLengthTokenizer và skip policy

Trong chunk-oriented step, lỗi độ dài dòng có thể phát sinh ở reader khi tokenizer không thể tách record. Nếu nghiệp vụ cho phép bỏ qua riêng dòng lỗi, có thể cấu hình skip cho exception phù hợp.

Ví dụ:

```java
return new StepBuilder("importEmployeesStep", jobRepository)
        .<Employee, Employee>chunk(200, transactionManager)
        .reader(employeeReader)
        .writer(employeeWriter)
        .faultTolerant()
        .skip(IncorrectLineLengthException.class)
        .skipLimit(20)
        .listener(employeeSkipListener)
        .build();
```

Đây chỉ phù hợp khi một dòng sai độ dài có thể được loại riêng và có quy trình lưu lại lỗi. Nếu toàn bộ file bị lệch format do cấu hình range sai hoặc dùng nhầm encoding, skip từng dòng có thể khiến hàng loạt record bị bỏ qua. Trong trường hợp đó nên để step thất bại để sửa cấu hình hoặc file nguồn.

`SkipListener.onSkipInRead` chỉ nhận exception vì reader chưa tạo được item. Với lỗi từ `FlatFileParseException` hoặc `IncorrectLineLengthException`, có thể lấy thông tin dòng/nguồn từ exception nếu phiên bản và loại exception cung cấp, nhưng cần kiểm tra API cụ thể trước khi sử dụng.

## 19. Những lỗi cấu hình thường gặp

| Vấn đề | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Các trường bị lệch từ một cột trở đi | Dùng vị trí 0-based hoặc tính sai điểm cuối inclusive. | Dùng range 1-based, inclusive và đối chiếu đặc tả. |
| Tên trường không khớp giá trị | Thứ tự `setNames` khác thứ tự `setColumns`. | Giữ hai danh sách cùng thứ tự và cùng số phần tử. |
| Trường cuối bị cắt thiếu | Range cuối kết thúc sớm hoặc file có độ dài khác đặc tả. | Kiểm tra range và độ dài thực tế; dùng range mở nếu format cho phép. |
| Reader lỗi với dòng ngắn | Strict mode phát hiện độ dài không hợp lệ. | Sửa nguồn/range hoặc tắt strict chỉ khi format cho phép và mapper xử lý phần thiếu. |
| Reader không phát hiện file sai cấu trúc | Đã tắt strict của tokenizer. | Bật strict và kiểm thử dòng sai độ dài. |
| Resource không tồn tại nhưng nhầm là lỗi tokenizer | Strict của reader và strict của tokenizer bị nhầm. | Phân biệt kiểm tra resource với kiểm tra record length. |
| Ngày hoặc số parse lỗi | Tokenizer cắt đúng nhưng format dữ liệu không đúng mapper. | Dùng formatter/parser theo đặc tả và validate giá trị. |
| Mất số 0 đầu của mã | Mapper chuyển mã sang số thay vì giữ String. | Giữ mã định danh dưới dạng String. |
| Ký tự có dấu bị lệch cột | Encoding sai hoặc đặc tả tính theo byte nhưng tokenizer cắt theo ký tự. | Cấu hình charset đúng và xác nhận đơn vị độ rộng. |
| Header bị parse như record | Chưa cấu hình `linesToSkip` hoặc header callback phù hợp. | Xử lý header ở reader trước tokenizer. |
| Bỏ qua hàng loạt record | Range sai hoặc file không đúng định dạng nhưng lỗi được skip quá rộng. | Dừng job, xác minh layout và thu hẹp skip policy. |

## 20. Quy trình xây dựng tokenizer từ đặc tả file

Khi nhận một file fixed-width mới, có thể triển khai theo trình tự:

1. **Lấy đặc tả bản ghi:** xác định tên trường, vị trí bắt đầu/kết thúc, độ dài và kiểu dữ liệu.
2. **Xác định đơn vị độ rộng:** byte, ký tự hay code unit; kiểm tra charset và dữ liệu Unicode.
3. **Lập bảng Range:** dùng vị trí 1-based, inclusive; tính lại độ dài từng trường.
4. **Xác định vùng bỏ qua:** reserved, filler, header, comment hoặc trailer.
5. **Cấu hình tokenizer:** khai báo `setNames`, `setColumns` và strict mode.
6. **Viết FieldSetMapper:** trim/preserve padding, parse ngày/số và validate dữ liệu.
7. **Tích hợp reader:** cấu hình resource, encoding, header, line mapper và checkpoint.
8. **Test dòng chuẩn:** xác nhận từng field cắt đúng vị trí.
9. **Test dòng biên:** ngắn, dài, blank, sai format, ký tự đặc biệt và range mở.
10. **Chọn fault tolerance:** quyết định lỗi record nào có thể skip và lỗi file/layout nào phải dừng.

Đặc biệt, hãy lưu một số dòng mẫu thực tế đã được xác nhận từ hệ thống nguồn làm fixture test. Test dựa trên chuỗi tự tạo chỉ có giá trị khi người viết đã chắc chắn vị trí và padding của chuỗi đó đúng với đặc tả.

## 21. Những điểm cần ghi nhớ

- `FixedLengthTokenizer` tách một dòng theo các khoảng vị trí cố định và trả về `FieldSet`.
- `Range` dùng vị trí 1-based, điểm cuối inclusive; độ dài là `end - start + 1`.
- `setNames` và `setColumns` phải có cùng số phần tử và cùng thứ tự.
- `DefaultLineMapper` kết hợp tokenizer với `FieldSetMapper` để tạo domain object.
- Tokenizer chỉ tách text; mapper chịu trách nhiệm trim, parse kiểu và validate dữ liệu.
- `setStrict(true)` kiểm tra độ dài dòng theo range; `strict` của FlatFileItemReader kiểm tra resource, hai cấu hình có ý nghĩa khác nhau.
- Range có thể bỏ qua vùng reserved hoặc dùng range mở cho trường cuối khi định dạng cho phép.
- Tokenizer cắt trên dòng `String` đã giải mã; nếu đặc tả fixed-width theo byte, phải xác minh encoding và byte boundary.
- Header, comment và dòng trống được xử lý ở reader, không phải bằng cách thay đổi range.
- Có thể dùng `BeanWrapperFieldSetMapper` cho JavaBean phù hợp hoặc viết `FieldSetMapper` riêng để kiểm soát conversion.
- Test tokenizer, mapper và reader ở các mức riêng; kiểm thử cả dòng chuẩn, dòng sai độ dài và giá trị không hợp lệ.
- Chỉ skip record sai khi nghiệp vụ cho phép; file lệch layout hoặc sai encoding diện rộng thường nên làm step thất bại.

`FixedLengthTokenizer` là lựa chọn phù hợp khi cấu trúc file được xác định bằng vị trí trường. Hãy chuyển đặc tả thành các `Range` chính xác, giữ thứ tự tên trường, tách rõ tokenization khỏi conversion và kiểm tra đơn vị độ rộng/encoding. Khi kết hợp với `FlatFileItemReader`, `DefaultLineMapper` và một `FieldSetMapper` có kiểm soát, ứng dụng có thể đọc file fixed-width rõ ràng và phát hiện sớm những record không tuân theo định dạng nguồn.
