# Kiểm thử reader với input biên

Trong Spring Batch, **ItemReader** đọc từng item từ một nguồn dữ liệu và trả về item tiếp theo cho Step. Khi nguồn đã hết, reader trả về **null** để báo kết thúc. Vì reader thường nằm ở đầu một pipeline chunk-oriented, lỗi tại đây có thể làm cả chunk không được xử lý hoặc khiến Job dừng trước khi writer ghi dữ liệu.

Kiểm thử reader với input biên giúp xác nhận reader hoạt động đúng ở những tình huống dễ bị bỏ sót: nguồn rỗng, chỉ có một bản ghi, số bản ghi nằm ngay trước hoặc sau ranh giới trang/chunk, dòng cuối không đầy đủ, trường dữ liệu trống, dữ liệu sai định dạng, file không tồn tại và restart từ trạng thái đã lưu.

Một bài kiểm thử tốt cần kiểm tra cả **giá trị được đọc**, **thứ tự**, **thời điểm reader trả null**, **exception khi dữ liệu không hợp lệ** và **khả năng khôi phục trạng thái**. Cũng cần phân biệt trách nhiệm của reader với processor: reader kiểm tra cấu trúc và chuyển đổi dữ liệu nguồn thành item; các quy tắc nghiệp vụ sâu hơn thường thuộc processor hoặc validator.

## 1. Hợp đồng của ItemReader

Hợp đồng cơ bản của ItemReader khá nhỏ:

~~~java
public interface ItemReader<T> {
    T read() throws Exception;
}
~~~

Mỗi lần gọi read():

- Trả về một item nếu còn dữ liệu.
- Trả về null khi không còn item.
- Có thể ném exception nếu không thể đọc hoặc chuyển đổi dữ liệu theo cấu hình.

Ví dụ reader đơn giản:

~~~java
ItemReader<String> reader = new ListItemReader<>(
        List.of("A", "B", "C"));

assertEquals("A", reader.read());
assertEquals("B", reader.read());
assertEquals("C", reader.read());
assertNull(reader.read());
~~~

Điểm kết thúc là một phần của hợp đồng. Reader không nên dùng một chuỗi rỗng, số 0 hoặc một đối tượng đặc biệt để biểu thị EOF nếu các giá trị đó vẫn có thể là dữ liệu hợp lệ. Trong Spring Batch, null có ý nghĩa rõ ràng: không còn item để đọc.

Với reader có trạng thái, chẳng hạn reader đọc file hoặc database theo trang, cần kiểm thử thêm vòng đời ItemStream:

- open(ExecutionContext): mở nguồn và khôi phục trạng thái.
- update(ExecutionContext): lưu checkpoint hiện tại.
- close(): giải phóng tài nguyên.

## 2. Xác định các nhóm input biên

Trước khi viết test, hãy liệt kê các ranh giới mà nguồn dữ liệu có thể gặp. Với một file khách hàng CSV, ma trận ban đầu có thể là:

| Nhóm | Input cần thử | Điều cần xác nhận |
|---|---|---|
| Số lượng | File rỗng | Reader kết thúc ngay, không tạo item |
| Số lượng | Chỉ một bản ghi | Đọc được một item rồi EOF |
| Số lượng | N-1, N, N+1 item | Không mất hoặc lặp item tại ranh giới |
| Cấu trúc | Chỉ có header | Không coi header là dữ liệu |
| Cấu trúc | Thiếu cột hoặc thừa cột | Hành vi parse đúng theo cấu hình |
| Nội dung | Trường rỗng hoặc chỉ có khoảng trắng | Ánh xạ đúng; quy tắc từ chối ở đúng tầng |
| Nội dung | Chuỗi dài nhất được hỗ trợ | Không cắt hoặc làm hỏng dữ liệu |
| Kiểu dữ liệu | Giá trị số/ngày ở min, max | Chuyển đổi đúng hoặc báo lỗi rõ ràng |
| Định dạng | Dấu phân cách nằm trong dấu nháy | Không tách nhầm cột |
| Định dạng | Dòng cuối không có newline | Vẫn đọc đủ bản ghi cuối |
| Nguồn | File không tồn tại hoặc không đọc được | Báo lỗi theo chính sách |
| Trạng thái | Restart sau khi lưu checkpoint | Tiếp tục từ vị trí đã lưu |

Không phải mọi trường hợp đều phải được kiểm thử ở cùng một lớp. Ví dụ, reader có thể đọc thành công một email rỗng vào object; processor mới là nơi loại khách hàng không có email. Test reader nên xác nhận đúng hành vi của reader, còn test processor xác nhận quy tắc nghiệp vụ.

## 3. Kiểm thử reader với danh sách trong bộ nhớ

Với logic đọc đơn giản, có thể dùng ListItemReader để kiểm thử hợp đồng ItemReader mà không cần file hoặc database.

Ví dụ kiểm thử EOF:

~~~java
class ListReaderTest {

    @Test
    void returnsItemsInOrderThenNull() throws Exception {
        ItemReader<String> reader =
                new ListItemReader<>(List.of("A", "B", "C"));

        assertEquals("A", reader.read());
        assertEquals("B", reader.read());
        assertEquals("C", reader.read());
        assertNull(reader.read());
        assertNull(reader.read());
    }

    @Test
    void emptyInputReturnsNullImmediately() throws Exception {
        ItemReader<String> reader =
                new ListItemReader<>(List.of());

        assertNull(reader.read());
    }

    @Test
    void singleItemIsReturnedExactlyOnce() throws Exception {
        ItemReader<Integer> reader =
                new ListItemReader<>(List.of(42));

        assertEquals(42, reader.read());
        assertNull(reader.read());
        assertNull(reader.read());
    }
}
~~~

Các test này xác nhận:

- Danh sách được đọc đúng thứ tự.
- Reader không tự tạo thêm item.
- Nguồn rỗng kết thúc ngay.
- Một item không bị trả về lặp lại sau EOF.

ListItemReader phù hợp để kiểm thử một phần logic điều phối hoặc code nhận ItemReader. Nó không thay thế test cho FlatFileItemReader, JdbcPagingItemReader hay reader tự viết, vì các reader đó còn có logic riêng về parsing, paging, cursor và trạng thái.

## 4. Kiểm thử FlatFileItemReader với file biên

Với file CSV, nên tạo fixture ngay trong test bằng JUnit 5 @TempDir. Như vậy test có thể kiểm soát chính xác nội dung file và không phụ thuộc vào file trên máy phát triển.

Giả sử dữ liệu có ba cột id, name và email. Tạo một JavaBean đơn giản để ánh xạ:

~~~java
public class CustomerRow {

    private Long id;
    private String name;
    private String email;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }
}
~~~

Tạo factory cho reader:

~~~java
private FlatFileItemReader<CustomerRow> createReader(Path file) {
    return new FlatFileItemReaderBuilder<CustomerRow>()
            .name("customerReader")
            .resource(new FileSystemResource(file.toFile()))
            .encoding("UTF-8")
            .linesToSkip(1)
            .delimited()
            .names("id", "name", "email")
            .targetType(CustomerRow.class)
            .saveState(true)
            .build();
}
~~~

Trong ví dụ:

- linesToSkip(1) bỏ qua header.
- names(...) xác định tên các trường.
- targetType(...) ánh xạ FieldSet vào bean.
- encoding("UTF-8") xác định encoding của file.
- saveState(true) cho phép reader lưu trạng thái phục vụ restart.
- name(...) cần ổn định để reader nhận diện trạng thái trong ExecutionContext.

Một test cho một bản ghi:

~~~java
class FlatFileCustomerReaderTest {

    @TempDir
    Path tempDir;

    private FlatFileItemReader<CustomerRow> createReader(Path file) {
        return new FlatFileItemReaderBuilder<CustomerRow>()
                .name("customerReader")
                .resource(new FileSystemResource(file.toFile()))
                .encoding("UTF-8")
                .linesToSkip(1)
                .delimited()
                .names("id", "name", "email")
                .targetType(CustomerRow.class)
                .saveState(true)
                .build();
    }

    @Test
    void readsOneRecordThenReturnsEof() throws Exception {
        Path file = tempDir.resolve("customers.csv");
        Files.writeString(
                file,
                "id,name,email\n" +
                "1,Alice,alice@example.com\n",
                StandardCharsets.UTF_8);

        FlatFileItemReader<CustomerRow> reader = createReader(file);

        reader.open(new ExecutionContext());
        try {
            CustomerRow customer = reader.read();

            assertNotNull(customer);
            assertEquals(1L, customer.getId());
            assertEquals("Alice", customer.getName());
            assertEquals("alice@example.com", customer.getEmail());

            assertNull(reader.read());
        } finally {
            reader.close();
        }
    }
}
~~~

Đóng reader trong finally để giải phóng resource kể cả khi assertion hoặc thao tác đọc thất bại. Với reader có mở file, cursor hoặc connection, việc đóng resource là một phần cần được kiểm thử.

### File rỗng và file chỉ có header

Hai trường hợp này không giống nhau:

- File rỗng có 0 byte.
- File chỉ có header có một dòng tiêu đề nhưng không có bản ghi.

Nếu reader được cấu hình bỏ qua một dòng header, cả hai trường hợp thường không tạo ra item. Test nên xác nhận read() trả null ngay sau open().

~~~java
@Test
void emptyFileReturnsEof() throws Exception {
    Path file = tempDir.resolve("empty.csv");
    Files.writeString(file, "", StandardCharsets.UTF_8);

    FlatFileItemReader<CustomerRow> reader = createReader(file);
    reader.open(new ExecutionContext());

    try {
        assertNull(reader.read());
    } finally {
        reader.close();
    }
}

@Test
void headerOnlyFileReturnsEof() throws Exception {
    Path file = tempDir.resolve("header-only.csv");
    Files.writeString(
            file,
            "id,name,email\n",
            StandardCharsets.UTF_8);

    FlatFileItemReader<CustomerRow> reader = createReader(file);
    reader.open(new ExecutionContext());

    try {
        assertNull(reader.read());
    } finally {
        reader.close();
    }
}
~~~

Nếu ứng dụng yêu cầu file phải có ít nhất một bản ghi, đó là một quy tắc nghiệp vụ hoặc kiểm tra đầu vào riêng. Reader trả EOF cho file không có dữ liệu là hành vi hợp lệ; không nên biến mọi file rỗng thành lỗi nếu yêu cầu nghiệp vụ không quy định như vậy.

## 5. Kiểm thử ranh giới số lượng N-1, N và N+1

Một lỗi phổ biến trong reader phân trang hoặc xử lý theo chunk là mất hoặc lặp item ngay tại ranh giới. Hãy chọn một kích thước N đại diện cho page size hoặc chunk size, sau đó thử:

- N-1 item: chưa đủ một nhóm.
- N item: vừa đúng một nhóm.
- N+1 item: một item dư tạo nhóm cuối.
- 2N item: vừa đúng hai nhóm.
- 2N+1 item: có nhóm cuối chỉ một item.

Với reader đơn giản, kiểm thử tổng số item và thứ tự:

~~~java
@ParameterizedTest
@ValueSource(ints = {0, 1, 9, 10, 11, 20, 21})
void readsEveryItemExactlyOnce(int itemCount) throws Exception {
    List<Integer> input = IntStream.rangeClosed(1, itemCount)
            .boxed()
            .toList();

    ItemReader<Integer> reader = new ListItemReader<>(input);
    List<Integer> actual = new ArrayList<>();

    Integer item;
    while ((item = reader.read()) != null) {
        actual.add(item);
    }

    assertEquals(input, actual);
    assertNull(reader.read());
}
~~~

Trong ví dụ này, N là 10. Test kiểm tra các kích thước 9, 10, 11, 20 và 21, cùng trường hợp rỗng và một item.

Lưu ý: chunk size thuộc cấu hình Step, còn reader thường chỉ biết cách trả item tiếp theo. Test reader độc lập xác nhận số lượng và thứ tự item. Nếu cần kiểm tra commit theo từng chunk, hãy viết thêm test tích hợp cho Step với chunk size cụ thể và writer ghi nhận các nhóm được nhận.

### Vì sao N+1 quan trọng?

Nếu reader dùng page size bằng 10, nguồn có 11 item, page đầu chứa 10 item và page tiếp theo chỉ có một item. Lỗi ở điều kiện chuyển trang có thể khiến item cuối bị bỏ qua hoặc item ở ranh giới bị trả lại hai lần.

Một bài test N+1 nên xác nhận:

- Item thứ N được trả đúng một lần.
- Item thứ N+1 được lấy từ trang tiếp theo.
- Sau item cuối, read() trả null.
- Không có truy vấn hoặc lần đọc vô hạn sau EOF.

## 6. Kiểm thử dữ liệu thiếu, thừa và sai định dạng

Reader file thường phải chuyển đổi chuỗi nguồn thành kiểu dữ liệu của item. Các trường hợp sau cần được thử riêng:

| Input | Câu hỏi cần xác nhận |
|---|---|
| Thiếu một cột | Parser ném exception hay áp dụng giá trị mặc định? |
| Thừa một cột | Parser từ chối hay bỏ qua phần dư theo cấu hình? |
| ID không phải số | Có báo lỗi chuyển đổi rõ ràng không? |
| Ngày sai định dạng | Reader có dừng với parse exception không? |
| Trường rỗng | Được ánh xạ thành chuỗi rỗng, null hay giá trị mặc định? |
| Dòng trắng | Bị bỏ qua, ánh xạ thành item hay báo lỗi? |
| Dấu phân cách trong dấu nháy | Có giữ nguyên nội dung một trường không? |
| Dấu nháy không đóng | Có báo lỗi parse không? |

Ví dụ test một dòng có ID không phải số:

~~~java
@Test
void invalidNumericFieldFailsReading() throws Exception {
    Path file = tempDir.resolve("invalid-id.csv");
    Files.writeString(
            file,
            "id,name,email\n" +
            "abc,Alice,alice@example.com\n",
            StandardCharsets.UTF_8);

    FlatFileItemReader<CustomerRow> reader = createReader(file);
    reader.open(new ExecutionContext());

    try {
        assertThrows(Exception.class, reader::read);
    } finally {
        reader.close();
    }
}
~~~

Trong test thực tế, nên kiểm tra loại exception cụ thể theo phiên bản Spring Batch và cách cấu hình FieldSetMapper. Lỗi parsing có thể được bọc trong FlatFileParseException, kèm thông tin dòng và nguyên nhân gốc. Nếu test chỉ quan tâm hợp đồng reader, assertThrows(Exception.class) là cách tổng quát; nếu cần kiểm tra chẩn đoán, hãy assert loại exception và line number.

Không nên mặc định mọi trường thiếu hoặc thừa đều phải bị từ chối. Hãy định nghĩa rõ schema đầu vào và cấu hình tokenizer, strict mode, mapper theo yêu cầu của ứng dụng.

## 7. Kiểm thử trường rỗng, khoảng trắng và giới hạn độ dài

Dữ liệu thực tế thường chứa các giá trị như:

- Chuỗi rỗng: trường không có ký tự.
- Khoảng trắng: một hoặc nhiều dấu cách.
- Tab hoặc ký tự xuống dòng không mong đợi.
- Chuỗi rất dài.
- Ký tự Unicode, dấu tiếng Việt hoặc emoji.
- Ký tự đặc biệt và dấu phân cách nằm trong nội dung.

Reader cần giữ hoặc ánh xạ dữ liệu đúng theo cấu hình. Nếu quy tắc nghiệp vụ yêu cầu trim, kiểm tra độ dài hoặc từ chối trường trống, hãy quyết định thành phần nào chịu trách nhiệm.

Ví dụ một test xác nhận reader giữ nguyên trường có dấu cách:

~~~java
@Test
void preservesWhitespaceForProcessorToValidate() throws Exception {
    Path file = tempDir.resolve("whitespace.csv");
    Files.writeString(
            file,
            "id,name,email\n" +
            "1,  Alice  ,alice@example.com\n",
            StandardCharsets.UTF_8);

    FlatFileItemReader<CustomerRow> reader = createReader(file);
    reader.open(new ExecutionContext());

    try {
        CustomerRow customer = reader.read();

        assertNotNull(customer);
        assertEquals("  Alice  ", customer.getName());
    } finally {
        reader.close();
    }
}
~~~

Test này có ý nghĩa nếu reader được cấu hình không tự trim trường. Nếu tokenizer hoặc mapper của ứng dụng đã chuẩn hóa dữ liệu, assertion cần phản ánh đúng cấu hình đó.

Với trường có giới hạn độ dài, hãy thử cả:

- Độ dài nhỏ nhất hợp lệ.
- Đúng giới hạn tối đa.
- Vượt giới hạn một ký tự.
- Chuỗi rỗng và chuỗi chỉ chứa khoảng trắng.

Nếu reader chỉ ánh xạ chuỗi, việc từ chối độ dài có thể thuộc processor hoặc validator. Hãy kiểm tra đúng nơi chịu trách nhiệm để tránh test sai tầng.

## 8. Kiểm thử ngày tháng, số và giá trị biên

Khi reader ánh xạ chuỗi sang kiểu dữ liệu, các giá trị sát giới hạn rất dễ làm lộ lỗi parse hoặc overflow.

Ví dụ với một trường số nguyên:

| Trường hợp | Ví dụ | Điều cần kiểm tra |
|---|---|---|
| Giá trị nhỏ nhất | 0 hoặc giá trị âm tối thiểu được hỗ trợ | Chuyển đổi đúng |
| Giá trị lớn nhất | MAX của kiểu đích | Không overflow |
| Vượt giới hạn | MAX + 1 | Báo lỗi rõ ràng |
| Giá trị âm | -1 | Được chấp nhận hay từ chối theo schema |
| Dấu cộng | +10 | Cách parser xử lý |
| Dấu thập phân | 10.25 | Có đúng kiểu và scale không? |

Với ngày tháng, thử:

- Ngày đầu và cuối của tháng.
- Ngày 29 tháng 2 trong năm nhuận.
- Ngày 29 tháng 2 trong năm không nhuận.
- Ngày 31 ở tháng chỉ có 30 ngày.
- Định dạng thiếu số 0 ở đầu.
- Chuỗi rỗng hoặc ngày không hợp lệ.

Nếu reader chỉ đọc chuỗi, parser có thể để việc chuyển đổi ngày cho processor. Nếu reader dùng FieldSetMapper để chuyển đổi ngay, test reader phải xác nhận hành vi parse của mapper. Hãy nhất quán với schema thực tế thay vì thêm quy tắc nghiệp vụ vào reader một cách tùy tiện.

## 9. Kiểm thử dấu phân cách, dấu nháy và encoding

File CSV không chỉ là các giá trị phân tách bằng dấu phẩy. Một trường có thể chứa dấu phẩy trong dấu nháy, dấu nháy được escape, hoặc ký tự Unicode.

Ví dụ:

~~~csv
id,name,email
1,"Nguyen, An",an@example.com
2,"He said ""Hello""",hello@example.com
3,"Nguyễn Thị Ánh",anh@example.com
~~~

Các test cần xác nhận:

- Dấu phẩy trong trường có nháy không tạo thêm cột.
- Dấu nháy kép được escape được đọc đúng.
- Ký tự tiếng Việt không bị lỗi encoding.
- File có BOM được xử lý theo cấu hình và phiên bản reader.
- Dòng kết thúc bằng LF hoặc CRLF đều được xử lý theo yêu cầu.
- Dòng cuối không có newline vẫn được đọc đủ.

Đừng chỉ dùng fixture được tạo bởi cùng một hàm serialize với code production. Nếu cả writer fixture và reader cùng hiểu sai định dạng theo một cách, test có thể vẫn xanh. Với format quan trọng, hãy giữ một số fixture mẫu độc lập được tạo theo schema của nguồn dữ liệu.

## 10. Kiểm thử file không tồn tại và nguồn không hợp lệ

Nguồn đầu vào có thể không tồn tại, không đọc được hoặc bị thay đổi trước khi Job chạy.

Với FlatFileItemReader, mặc định strict mode thường yêu cầu resource tồn tại. Có thể kiểm tra trường hợp thiếu file:

~~~java
@Test
void missingFileFailsWhenStrictModeIsEnabled() {
    Path file = tempDir.resolve("does-not-exist.csv");
    FlatFileItemReader<CustomerRow> reader = createReader(file);

    assertThrows(
            IllegalStateException.class,
            () -> reader.open(new ExecutionContext()));
}
~~~

Nếu ứng dụng cấu hình strict(false), file không tồn tại có thể được xử lý như nguồn rỗng tùy reader. Chỉ sử dụng chế độ đó khi nghiệp vụ thực sự coi file thiếu là hợp lệ.

Các trường hợp nguồn cần cân nhắc:

- Đường dẫn sai.
- File không tồn tại.
- Đường dẫn trỏ tới thư mục thay vì file.
- Quyền đọc bị từ chối.
- File rỗng hoặc file bị cắt giữa chừng.
- File thay đổi trong lúc Job đang chạy.
- Resource từ xa không phản hồi hoặc timeout.

Không nên kiểm thử quyền truy cập hệ điều hành bằng cách giả định một user cụ thể trên mọi môi trường CI. Với tình huống này, có thể kiểm thử qua abstraction hoặc resource giả lập, rồi bổ sung một kiểm thử môi trường phù hợp nếu cần.

## 11. Kiểm thử reader phân trang với page boundary

Với reader đọc database theo trang, page size tạo ra một ranh giới quan trọng. Giả sử page size là 10, hãy thử tập dữ liệu có 0, 1, 9, 10, 11, 20 và 21 bản ghi.

Điều cần xác nhận:

- Trang đầu rỗng kết thúc đúng.
- Một trang chưa đầy được đọc hết.
- Khi số bản ghi đúng bằng page size, không phát sinh trang thừa có item lặp.
- Khi có page size + 1 bản ghi, item đầu tiên của trang kế tiếp không bị bỏ sót.
- Trang cuối có thể nhỏ hơn page size.
- Thứ tự đọc ổn định giữa các trang.

Một truy vấn phân trang cần có thứ tự xác định, thường bao gồm khóa duy nhất làm tiêu chí cuối cùng. Nếu chỉ sort theo một cột không duy nhất, hai bản ghi có cùng giá trị sort có thể đổi thứ tự giữa các trang, dẫn đến bỏ sót hoặc lặp trong một số tình huống.

Ví dụ một test tích hợp có thể đọc toàn bộ reader và so sánh ID theo thứ tự mong đợi:

~~~java
List<Long> actualIds = new ArrayList<>();
Long id;

while ((id = reader.read()) != null) {
    actualIds.add(id);
}

assertEquals(expectedIds, actualIds);
assertEquals(expectedIds.size(), new HashSet<>(actualIds).size());
~~~

Assertion thứ hai giúp phát hiện ID trùng trong kết quả. Với database reader, nên dùng database test riêng hoặc embedded database để kiểm soát dữ liệu, thay vì phụ thuộc vào database dùng chung của môi trường.

### Paging và dữ liệu thay đổi

Nếu nguồn database thay đổi trong lúc reader chuyển trang, kết quả có thể phụ thuộc isolation level, query và chiến lược phân trang. Test nên mô phỏng việc thêm hoặc xóa dữ liệu giữa các lần đọc trang nếu Job cần xử lý một snapshot nhất quán.

Đối với dữ liệu lớn, có thể dùng khóa tăng dần hoặc keyset pagination để giảm rủi ro dịch chuyển offset. Dù dùng cách nào, hãy định nghĩa rõ tập dữ liệu thuộc về lần chạy và thứ tự đọc mong đợi.

## 12. Kiểm thử restart và ExecutionContext

Reader có trạng thái cần được kiểm tra qua vòng đời open/update/close. Một test restart cơ bản:

1. Tạo reader với một file có nhiều bản ghi.
2. Mở reader bằng ExecutionContext rỗng.
3. Đọc một hoặc nhiều item.
4. Gọi update() để ghi checkpoint vào context.
5. Đóng reader.
6. Tạo reader mới với cùng tên và cùng nguồn.
7. Mở reader mới bằng context đã lưu.
8. Xác nhận item tiếp theo đúng vị trí mong đợi.

Ví dụ:

~~~java
@Test
void resumesFromSavedExecutionContext() throws Exception {
    Path file = tempDir.resolve("restart.csv");
    Files.writeString(
            file,
            "id,name,email\n" +
            "1,Alice,alice@example.com\n" +
            "2,Bob,bob@example.com\n" +
            "3,Carol,carol@example.com\n",
            StandardCharsets.UTF_8);

    ExecutionContext context = new ExecutionContext();

    FlatFileItemReader<CustomerRow> firstReader = createReader(file);
    firstReader.open(context);

    try {
        assertEquals(1L, firstReader.read().getId());

        firstReader.update(context);
    } finally {
        firstReader.close();
    }

    FlatFileItemReader<CustomerRow> restartedReader = createReader(file);
    restartedReader.open(context);

    try {
        assertEquals(2L, restartedReader.read().getId());
        assertEquals(3L, restartedReader.read().getId());
        assertNull(restartedReader.read());
    } finally {
        restartedReader.close();
    }
}
~~~

Test này mô phỏng việc reader lưu trạng thái và được mở lại với cùng ExecutionContext. Trong ứng dụng thực tế, Spring Batch điều phối việc gọi update và lưu context tại checkpoint của Step. Test tích hợp Step sẽ xác nhận thêm mối liên hệ giữa checkpoint, transaction và JobRepository.

Không dùng cùng ExecutionContext cho một reader khác tên nếu muốn kiểm tra trạng thái restart bình thường. Tên stream ổn định là một phần quan trọng để reader tìm lại trạng thái đã lưu.

### Kiểm thử thay đổi nguồn sau checkpoint

Sau khi lưu checkpoint, hãy thử thay file đầu vào hoặc thay nội dung tại vị trí đã lưu. Reader có thể tiếp tục từ vị trí cũ nhưng dữ liệu không còn giống lần chạy trước.

Nếu Job yêu cầu nguồn bất biến, nên lưu checksum, phiên bản file hoặc mã nguồn dữ liệu trong JobParameters/metadata và xác minh trước khi restart. Test nên xác nhận Job từ chối hoặc xử lý theo chính sách nếu nguồn không còn khớp.

## 13. Kiểm thử reader trong Step thực tế

Test reader độc lập không xác nhận toàn bộ hành vi chunk. Để kiểm tra reader được gọi bởi Step, có thể dùng Spring Batch Test và khởi chạy Job hoặc Step với dữ liệu fixture.

Một test tích hợp thường xác nhận:

- Reader được mở và đóng đúng.
- Step đọc hết số item mong đợi.
- Processor nhận đúng item.
- Writer ghi đúng số lượng và thứ tự.
- StepExecution có readCount, writeCount và filterCount phù hợp.
- Step kết thúc với BatchStatus và ExitStatus mong đợi.
- Restart sử dụng checkpoint đã lưu.

Có thể dùng JobLauncherTestUtils để chạy Job, hoặc StepScopeTestUtils khi cần tạo ngữ cảnh Step cho bean StepScope. Tên và cách cấu hình test utility phụ thuộc phiên bản Spring Batch Test đang dùng.

Ví dụ kiểm tra kết quả Step sau khi chạy Job:

~~~java
JobExecution execution =
        jobLauncherTestUtils.launchJob(parameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());

StepExecution stepExecution = execution.getStepExecutions()
        .stream()
        .filter(step -> "importCustomersStep".equals(step.getStepName()))
        .findFirst()
        .orElseThrow();

assertEquals(11, stepExecution.getReadCount());
assertEquals(11, stepExecution.getWriteCount());
~~~

Ví dụ trên giả định không có processor filter, skip hoặc writer bỏ qua item. Nếu có những hành vi đó, hãy điều chỉnh assertion theo quy tắc thực tế. Test tích hợp nên dùng database riêng và dữ liệu được tạo rõ ràng để kết quả không phụ thuộc vào lần chạy trước.

## 14. Kiểm thử reader tự viết

Nếu ứng dụng có reader tùy chỉnh, hãy kiểm thử các tình huống cụ thể của thuật toán đọc.

Ví dụ reader đọc theo ID tăng dần từ repository:

~~~java
public class CustomerRepositoryReader implements ItemReader<Customer> {

    private final CustomerRepository repository;
    private long lastId;

    public CustomerRepositoryReader(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public Customer read() {
        Customer next = repository.findNextAfter(lastId);

        if (next == null) {
            return null;
        }

        lastId = next.getId();
        return next;
    }
}
~~~

Các test cần bao gồm:

- Repository không có dữ liệu.
- Chỉ có một bản ghi.
- Có nhiều bản ghi với ID liên tiếp.
- ID có khoảng trống.
- Hai bản ghi có giá trị sắp xếp giống nhau.
- Bản ghi cuối cùng đúng tại giới hạn trang.
- Truy vấn repository ném exception.
- Dữ liệu mới xuất hiện trong lúc reader đang chạy.
- Reader được mở lại với checkpoint cũ nếu có hỗ trợ ItemStream.

Dùng Mockito để kiểm tra cách reader gọi repository:

~~~java
@Test
void returnsNullWhenRepositoryHasNoNextCustomer() {
    CustomerRepository repository = mock(CustomerRepository.class);
    when(repository.findNextAfter(0L)).thenReturn(null);

    CustomerRepositoryReader reader =
            new CustomerRepositoryReader(repository);

    assertNull(reader.read());

    verify(repository).findNextAfter(0L);
}
~~~

Với reader có trạng thái, hãy kiểm tra riêng việc khôi phục checkpoint. Không chỉ test số item trả về; hãy xác nhận thứ tự, điều kiện truy vấn và việc reader không bỏ qua hoặc lặp bản ghi tại ranh giới.

## 15. Phân biệt lỗi reader với lỗi processor

Một số lỗi xuất hiện gần nhau trong pipeline nhưng thuộc các tầng khác nhau:

| Tình huống | Tầng nên chịu trách nhiệm |
|---|---|
| File không tồn tại | Reader hoặc bước kiểm tra đầu vào |
| Dòng CSV thiếu cột | Reader/parser |
| ID không thể chuyển sang số | Reader/FieldSetMapper nếu chuyển đổi tại đây |
| Email sai quy tắc nghiệp vụ | Processor hoặc validator |
| Khách hàng đã tồn tại | Processor hoặc writer tùy quy tắc |
| Database mất kết nối khi insert | Writer/transaction infrastructure |
| Dữ liệu được đọc lặp do paging sai | Reader/query |
| Dữ liệu không thể restart | Reader state/ExecutionContext/JobRepository |

Nếu test reader đang assert một quy tắc thuộc processor, test sẽ trở nên khó hiểu và dễ gắn chặt vào implementation. Hãy đặt assertion tại đúng thành phần có trách nhiệm.

## 16. Tổ chức fixture và test dễ bảo trì

Một bộ test reader tốt thường có:

- Factory tạo reader với cấu hình giống production.
- Fixture nhỏ, tên rõ ràng và chứa đúng trường hợp đang kiểm tra.
- Test riêng cho EOF, parsing, mapping, resource và restart.
- Dữ liệu biên được tạo trong thư mục tạm.
- Assertion về thứ tự và số lượng, không chỉ kiểm tra item đầu tiên.
- Cleanup resource trong finally hoặc try-with-resources nếu abstraction hỗ trợ.
- Test tích hợp với database độc lập khi reader truy vấn database.

Không nên gom tất cả input biên vào một test dài. Khi một assertion thất bại, tên test nên chỉ ra tình huống nào bị lỗi, ví dụ emptyFileReturnsEof hoặc resumesFromSavedExecutionContext.

Với nhiều biến thể dữ liệu, JUnit parameterized tests giúp giảm code lặp. Tuy nhiên, mỗi case vẫn cần có tên hoặc dữ liệu đầu vào đủ rõ để đọc kết quả test.

## 17. Những lỗi kiểm thử thường gặp

### Chỉ kiểm tra item đầu tiên

Reader có thể đọc đúng item đầu nhưng bỏ sót item cuối hoặc lặp item ở trang tiếp theo. Hãy đọc đến EOF và so sánh toàn bộ danh sách.

### Không gọi close()

Reader mở file hoặc cursor nhưng test không đóng resource. Điều này có thể gây rò rỉ file handle và làm test thất bại ngẫu nhiên trên CI.

### Chỉ test file hợp lệ

Nguồn rỗng, header-only, dòng sai định dạng, trường trống và dòng cuối không newline mới là những trường hợp dễ phát hiện lỗi parser.

### Nhầm chunk size với số item reader đọc

Reader trả từng item. Chunk size quyết định số item được gom cho một lần xử lý transaction của Step. Test reader độc lập không thể thay thế test transaction của Step.

### Dùng fixture quá giống code tạo dữ liệu production

Nếu test tạo file bằng cùng logic serializer đang được kiểm thử, hai phía có thể cùng mắc lỗi định dạng. Nên có fixture độc lập hoặc dữ liệu mẫu được viết rõ ràng.

### Không kiểm tra thứ tự

Một reader phân trang có thể trả đủ số item nhưng sai thứ tự hoặc lặp ID. Hãy xác nhận danh sách ID thực tế đúng với thứ tự mong đợi.

### Không kiểm tra trạng thái restart

Một reader có thể đọc đúng trong lần đầu nhưng không khôi phục được vị trí sau khi Job restart. Hãy test ItemStream và ExecutionContext nếu reader cần hỗ trợ restart.

## 18. Cách lập ma trận test cho reader

Với một reader thực tế, có thể lập ma trận nhỏ theo nguồn dữ liệu và ranh giới:

| Nhóm | Case tối thiểu | Assertion chính |
|---|---|---|
| EOF | 0 item, 1 item | null đúng thời điểm |
| Số lượng | N-1, N, N+1 | Không thiếu hoặc lặp item |
| File | Missing, empty, header-only | Hành vi resource và EOF |
| Parse | Thiếu cột, thừa cột, sai kiểu | Exception hoặc mapping theo cấu hình |
| Text | Rỗng, whitespace, Unicode, chuỗi dài | Giá trị được giữ/chuẩn hóa đúng |
| CSV | Quoted delimiter, escaped quote | Ranh giới cột chính xác |
| Paging | 0, 1, pageSize-1, pageSize, pageSize+1 | Không mất item qua trang |
| Restart | Lưu và mở lại ExecutionContext | Tiếp tục đúng vị trí |
| Resource | Đọc xong, exception giữa chừng | close được gọi và tài nguyên giải phóng |

Không cần tạo hàng trăm test cho mọi tổ hợp. Hãy chọn case theo rủi ro của nguồn dữ liệu và các nhánh logic trong reader. Với parser phức tạp hoặc nguồn không ổn định, bổ sung test theo từng quy tắc cụ thể.

## 19. Quy trình kiểm thử reader trước khi đưa vào Job

Một trình tự thực tế:

1. Xác định schema và quy tắc EOF của nguồn.
2. Viết test cho nguồn rỗng, một item và dữ liệu ở ranh giới N-1/N/N+1.
3. Kiểm thử parsing, kiểu dữ liệu, trường trống và encoding.
4. Kiểm thử nguồn thiếu hoặc lỗi truy cập.
5. Kiểm thử thứ tự, phân trang và dữ liệu cuối trang.
6. Nếu reader có trạng thái, kiểm thử open/update/close và restart.
7. Chạy reader trong Step với transaction manager và writer thực tế hoặc fixture tương đương.
8. Kiểm tra StepExecution counters và kết quả cuối.
9. Mô phỏng lỗi giữa chunk để xác nhận rollback và restart đúng như thiết kế.

Khi một test thất bại, hãy xác định lỗi nằm ở việc lấy dữ liệu, parsing, mapping, paging hay khôi phục trạng thái. Một reader đáng tin cậy phải trả đúng từng item, giữ thứ tự đã định nghĩa, báo EOF chính xác và có hành vi rõ ràng khi nguồn đầu vào nằm ở ranh giới hoặc không hợp lệ.
