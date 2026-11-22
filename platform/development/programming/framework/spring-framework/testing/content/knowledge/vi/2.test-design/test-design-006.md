# Dữ liệu chuẩn bị (fixture) tối thiểu và dễ đọc

Một bài kiểm thử chỉ có thể cho kết quả đáng tin cậy khi trạng thái ban đầu của nó rõ ràng. Nếu dữ liệu chuẩn bị quá nhiều, người đọc khó nhận ra phần nào thực sự ảnh hưởng đến kết quả. Nếu dữ liệu thiếu hoặc không hợp lệ, bài kiểm thử có thể thất bại vì cách chuẩn bị thay vì vì hành vi đang được kiểm tra.

Trong Spring Framework Testing, *fixture* là dữ liệu và trạng thái được chuẩn bị để một bài kiểm thử có thể thực hiện tình huống của nó. Fixture có thể gồm đối tượng miền, bản ghi trong cơ sở dữ liệu, request, cấu hình hoặc các thành phần phụ thuộc giả lập. Mục tiêu là tạo ra đúng bối cảnh cần thiết để kiểm tra một hành vi, với cách viết đủ rõ để người đọc hiểu ngay tình huống.

## 1. Fixture là gì?

Hãy hình dung bài kiểm thử cần xác nhận rằng hệ thống có thể giữ lại hai sản phẩm trong kho khi số lượng tồn lớn hơn số lượng yêu cầu. Trước khi gọi hành vi cần kiểm tra, bài test phải có một đối tượng kho với mã sản phẩm và số lượng ban đầu. Đó là dữ liệu fixture.

Một bài kiểm thử thường có ba bước:

1. **Arrange:** chuẩn bị fixture, đầu vào và các phụ thuộc cần thiết.
2. **Act:** thực hiện hành động đang được kiểm tra.
3. **Assert:** kiểm tra kết quả quan sát được.

Ví dụ:

```java
@Test
void reservesRequestedQuantityWhenStockIsAvailable() {
    Stock stock = new Stock("BOOK-01", 5);

    boolean reserved = stock.reserve(2);

    assertTrue(reserved);
    assertEquals(3, stock.getAvailableQuantity());
}
```

Trong ví dụ này, `new Stock("BOOK-01", 5)` là phần chuẩn bị fixture. Lời gọi `stock.reserve(2)` là hành động. Hai assertion xác nhận kết quả.

Fixture không nhất thiết là một lớp riêng hoặc một file dữ liệu riêng. Nó có thể chỉ là vài dòng khởi tạo ngay trong test. Điều quan trọng là trạng thái ban đầu phải dễ hiểu và phục vụ đúng tình huống cần kiểm tra.

## 2. Vì sao fixture nên tối thiểu?

Fixture tối thiểu chỉ chứa những dữ liệu cần thiết để tạo ra trạng thái hợp lệ và kích hoạt hành vi đang kiểm tra. Tối thiểu không có nghĩa là tạo đối tượng thiếu thuộc tính bắt buộc hoặc bỏ qua quy tắc miền. Nó có nghĩa là không đưa thêm dữ liệu không liên quan.

Giả sử test chỉ kiểm tra việc đặt trước tồn kho cho một mã sản phẩm. Nếu fixture tạo thêm khách hàng, địa chỉ giao hàng, hóa đơn, chương trình khuyến mãi và nhiều sản phẩm khác, người đọc phải tìm hiểu một lượng thông tin không góp phần giải thích kết quả.

Fixture nhỏ giúp:

- Nhìn thấy ngay điều kiện quan trọng của tình huống.
- Hiểu vì sao kết quả mong đợi là hợp lý.
- Xác định nhanh dữ liệu nào cần thay đổi khi test thất bại.
- Giảm các phụ thuộc và trạng thái có thể gây ảnh hưởng ngoài ý muốn.
- Giúp bài kiểm thử ít bị hỏng khi những thuộc tính không liên quan của mô hình thay đổi.

Có thể dùng câu hỏi sau để quyết định một giá trị có cần xuất hiện trong fixture hay không: **Nếu bỏ giá trị này, bài kiểm thử có còn tạo được trạng thái hợp lệ và kiểm tra đúng hành vi đó không?** Nếu câu trả lời là có, giá trị ấy có thể không cần thiết trong fixture của test này.

Ngược lại, không nên bỏ một trường chỉ vì assertion không đọc trực tiếp trường đó. Trường ấy có thể là điều kiện bắt buộc để tạo một đối tượng hợp lệ, để lưu dữ liệu qua JPA hoặc để đi qua validation của Spring MVC. Fixture phải đáp ứng các bất biến của miền và hợp đồng của thành phần đang kiểm tra.

## 3. Những đặc điểm của fixture dễ đọc

### Chỉ rõ dữ liệu quyết định kết quả

Tên biến và giá trị nên giúp người đọc nhận ra điều kiện của test. Ví dụ, `availableQuantity = 5` và `requestedQuantity = 2` dễ hiểu hơn những con số nằm rải rác trong nhiều lời gọi mà không có ngữ cảnh.

Nếu test có nhiều dữ liệu, có thể đặt tên theo ý nghĩa:

```java
int availableQuantity = 5;
int requestedQuantity = 2;

Stock stock = new Stock("BOOK-01", availableQuantity);

boolean reserved = stock.reserve(requestedQuantity);
```

Cách này hữu ích khi giá trị được dùng nhiều lần hoặc tên biến làm rõ điều kiện nghiệp vụ. Với một phép thử rất ngắn, truyền trực tiếp giá trị vào constructor có thể gọn và vẫn dễ hiểu. Không cần tạo biến chỉ để thay thế mọi literal.

### Dùng giá trị đại diện, ổn định

Giá trị fixture nên làm rõ tình huống, không cần giống dữ liệu production. Dùng mã như `BOOK-01`, email thuộc miền `example.test`, hoặc ngày giờ cố định sẽ giúp người đọc nhận ra dữ liệu kiểm thử và tránh phụ thuộc vào thông tin thật.

Tránh tạo dữ liệu ngẫu nhiên nếu tính ngẫu nhiên không phải điều đang được kiểm tra. Khi test thất bại, dữ liệu cố định giúp tái hiện và phân tích nguyên nhân dễ hơn.

### Tôn trọng quy tắc của mô hình

Nếu một đối tượng yêu cầu mã định danh, trạng thái và các dòng hàng hợp lệ, fixture phải cung cấp các giá trị hợp lệ đó. Không nên dùng reflection để bỏ qua constructor, tắt validation hoặc tạo một trạng thái mà ứng dụng không thể đạt được trong hoạt động bình thường.

Một fixture hợp lệ giúp bài kiểm thử quan sát hành vi thật của hệ thống. Fixture không hợp lệ có thể làm test thất bại ở một điểm không thuộc mục tiêu của nó.

### Đặt dữ liệu gần nơi sử dụng

Nếu chỉ một test cần một dữ liệu đặc biệt, hãy khai báo dữ liệu đó ngay trong test. Người đọc có thể xem phần Arrange và biết ngay điều kiện của tình huống mà không phải nhảy sang nhiều helper hoặc lớp cấu hình.

Khi nhiều test cùng dùng một fixture có ý nghĩa giống nhau, hãy cân nhắc trích xuất thành phương thức tạo dữ liệu. Phương thức nên có tên mô tả trạng thái được tạo ra.

## 4. Bắt đầu bằng fixture trực tiếp trong test

Cách đơn giản nhất thường là khởi tạo đối tượng ngay trong phần Arrange. Cách này đặc biệt phù hợp với unit test có ít đối tượng và constructor ngắn.

Ví dụ, một bài kiểm thử service có thể dùng Mockito để thay thế repository:

```java
@ExtendWith(MockitoExtension.class)
class InventoryServiceTest {

    @Mock
    private StockRepository stockRepository;

    @InjectMocks
    private InventoryService inventoryService;

    @Test
    void reservesRequestedQuantityWhenStockIsAvailable() {
        Stock stock = new Stock("BOOK-01", 5);

        when(stockRepository.findBySku("BOOK-01"))
                .thenReturn(Optional.of(stock));

        boolean reserved = inventoryService.reserve("BOOK-01", 2);

        assertTrue(reserved);
        assertEquals(3, stock.getAvailableQuantity());
        verify(stockRepository).save(stock);
    }
}
```

Fixture chính của test là đối tượng `Stock` có năm đơn vị hàng. Repository mock được cấu hình để trả về đúng đối tượng đó khi service tìm mã `BOOK-01`. Hành động yêu cầu đặt trước hai đơn vị; kết quả cần quan sát là thao tác thành công, số lượng còn lại bằng ba và repository lưu đối tượng đã thay đổi.

Ví dụ giả định `InventoryService` sử dụng `StockRepository` để tìm và lưu kho, còn `Stock.reserve` cập nhật số lượng khi có đủ hàng. Các lớp miền và repository được lược bớt để tập trung vào cách chuẩn bị dữ liệu.

Dữ liệu được viết ngay tại test nên không cần tìm một helper khác để biết kho ban đầu có bao nhiêu hàng. Nếu chỉ có một test dùng tình huống này, cách viết trực tiếp thường là lựa chọn dễ đọc nhất.

## 5. Trích xuất phương thức tạo fixture khi có sự lặp lại

Khi nhiều test cần tạo cùng một loại đối tượng, việc lặp lại constructor dài có thể làm phần Arrange trở nên khó đọc. Khi đó, một phương thức factory nhỏ giúp gom cách tạo đối tượng vào một chỗ.

Ví dụ:

```java
private static Stock stockWithAvailableUnits(int quantity) {
    return new Stock("BOOK-01", quantity);
}
```

Test có thể viết:

```java
@Test
void rejectsReservationWhenStockIsInsufficient() {
    Stock stock = stockWithAvailableUnits(1);

    when(stockRepository.findBySku("BOOK-01"))
            .thenReturn(Optional.of(stock));

    boolean reserved = inventoryService.reserve("BOOK-01", 2);

    assertFalse(reserved);
    assertEquals(1, stock.getAvailableQuantity());
    verify(stockRepository, never()).save(stock);
}
```

Tên `stockWithAvailableUnits` cho biết phương thức tạo ra đối tượng nào và tham số `quantity` thể hiện điều kiện thay đổi giữa các tình huống. Người đọc có thể hiểu ngay fixture này đại diện cho kho chỉ còn một đơn vị.

Một factory tốt nên có phạm vi nhỏ và mục đích cụ thể:

- Tên mô tả trạng thái hoặc vai trò của đối tượng.
- Tham số đại diện cho những yếu tố mà từng test cần thay đổi.
- Giá trị mặc định bên trong là hợp lệ và ổn định.
- Không thực hiện thêm hành động nghiệp vụ hoặc truy cập hệ thống bên ngoài.
- Không che giấu những điều kiện quan trọng của tình huống.

Tránh các tên chung chung như `createData()`, `prepare()` hoặc `buildObject()` nếu chúng không cho biết dữ liệu nào sẽ được tạo. Cũng nên tránh phương thức có quá nhiều tham số boolean, vì lời gọi như `createOrder(true, false, true, false)` không thể hiện rõ trạng thái mong muốn.

Nếu chỉ một test sử dụng fixture, không cần trích xuất phương thức chỉ để giảm vài dòng. Một helper không làm cho test dễ đọc hơn nếu người đọc phải mở nó mới hiểu điều kiện ban đầu.

## 6. Khi nào nên dùng Builder hoặc Test Data Builder?

Một đối tượng có nhiều thuộc tính có thể khiến constructor dài và khó nhận biết giá trị nào quan trọng. Builder có thể giúp mô tả dữ liệu theo tên thuộc tính:

```java
Order order = Order.builder()
        .id("ORDER-100")
        .customerId("CUSTOMER-42")
        .status(OrderStatus.DRAFT)
        .build();
```

Đoạn code dễ đọc hơn constructor có nhiều tham số cùng kiểu. Tuy nhiên, builder không tự động làm fixture tốt hơn. Nếu một đối tượng chỉ có hai trường, tạo builder và một lớp helper riêng có thể khiến bài test dài và khó theo dõi hơn.

Một *Test Data Builder* là builder được đặt trong mã kiểm thử để tạo những biến thể dữ liệu phục vụ nhiều tình huống. Ví dụ, builder có thể cung cấp một đơn hàng hợp lệ mặc định, sau đó cho phép test thay đổi trạng thái hoặc khách hàng cần thiết.

```java
private static OrderBuilder aDraftOrder() {
    return Order.builder()
            .id("ORDER-100")
            .customerId("CUSTOMER-42")
            .status(OrderStatus.DRAFT);
}
```

Nếu builder trả về một builder thật, test có thể bổ sung thuộc tính trước khi gọi `build()`:

```java
Order order = aDraftOrder()
        .customerId("CUSTOMER-99")
        .build();
```

Ví dụ này minh họa cách tổ chức; `OrderBuilder` phụ thuộc vào API builder mà mô hình dự án cung cấp.

Builder phù hợp khi:

- Đối tượng có nhiều thuộc tính và constructor khó đọc.
- Nhiều test cần các biến thể của cùng một đối tượng.
- Một số thuộc tính có giá trị mặc định hợp lệ.
- Test cần thay đổi có chủ đích một vài thuộc tính mà không lặp lại toàn bộ dữ liệu.

Khi dùng builder, hãy để những thuộc tính quan trọng của tình huống xuất hiện rõ trong test. Nếu trạng thái đơn hàng là điều kiện quyết định kết quả, hãy viết `.status(OrderStatus.DRAFT)` hoặc một phương thức có tên tương đương, thay vì để trạng thái mặc định ẩn trong builder.

## 7. Dùng @BeforeEach đúng phạm vi

JUnit Jupiter cung cấp `@BeforeEach` để chạy phương thức chuẩn bị trước mỗi test method. Đây là nơi phù hợp cho fixture chung mà phần lớn test trong lớp đều cần.

```java
@ExtendWith(MockitoExtension.class)
class InventoryServiceTest {

    @Mock
    private StockRepository stockRepository;

    @InjectMocks
    private InventoryService inventoryService;

    private Stock stock;

    @BeforeEach
    void setUp() {
        stock = new Stock("BOOK-01", 5);
    }

    @Test
    void reservesAvailableStock() {
        when(stockRepository.findBySku("BOOK-01"))
                .thenReturn(Optional.of(stock));

        boolean reserved = inventoryService.reserve("BOOK-01", 2);

        assertTrue(reserved);
        assertEquals(3, stock.getAvailableQuantity());
    }
}
```

Mỗi test method nhận một đối tượng `Stock` mới vì `@BeforeEach` chạy trước từng test. Điều này giúp tránh việc test trước thay đổi số lượng rồi ảnh hưởng đến test sau.

Tuy nhiên, không nên đưa mọi dữ liệu của mọi tình huống vào `setUp()`. Nếu chỉ một test cần kho trống, hãy tạo trạng thái đó trong chính test hoặc dùng factory có tham số. Nếu `setUp()` tạo nhiều đối tượng mà test không sử dụng, người đọc khó xác định điều kiện thực sự của từng tình huống.

Một quy tắc thực tế là: dùng `@BeforeEach` cho phần nền chung, còn dữ liệu đặc thù của từng test đặt gần test đó. Khi một lớp có các nhóm test với fixture rất khác nhau, có thể tách lớp test theo hành vi để mỗi lớp có phần chuẩn bị gọn hơn.

### Phân biệt @BeforeEach và @BeforeAll

`@BeforeEach` chạy trước từng test method và thường thích hợp để tạo đối tượng có thể thay đổi.

`@BeforeAll` chạy một lần trước các test trong lớp. Nó có thể phù hợp cho dữ liệu dùng chung bất biến hoặc thao tác khởi tạo tốn kém. Với JUnit Jupiter, phương thức `@BeforeAll` thông thường phải là static, trừ khi lớp dùng lifecycle `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`.

Không nên đặt một đối tượng mutable dùng chung trong `@BeforeAll` nếu mỗi test có thể sửa nó. Chia sẻ trạng thái như vậy khiến kết quả phụ thuộc vào thứ tự chạy và làm test khó tái hiện.

## 8. Fixture trong các bài kiểm thử Spring

Fixture trong Spring test có thể là đối tượng Java, request gửi qua MockMvc hoặc bản ghi được lưu trong cơ sở dữ liệu kiểm thử. Cách chuẩn bị phụ thuộc vào phạm vi mà bài test muốn xác nhận.

### Với unit test cho service

Tạo trực tiếp đối tượng miền và cấu hình các phụ thuộc mock. Chỉ tạo những đối tượng cần thiết cho nhánh nghiệp vụ đang kiểm tra. Mock nên trả về dữ liệu cụ thể và dễ hiểu, thay vì một chuỗi hành vi dài không liên quan.

### Với MVC slice test

Một bài test dùng `@WebMvcTest` có thể chuẩn bị request body, query parameter hoặc dữ liệu trả về từ service mock. Request nên chứa các trường cần cho tình huống hiện tại. Nếu test đang kiểm tra validation của trường bắt buộc, dữ liệu thiếu trường đó là chủ đích; các trường còn lại vẫn nên hợp lệ để lỗi được quan sát thuộc đúng điều kiện đang thử.

Ví dụ, test cho endpoint tạo đơn hàng có thể dùng một JSON ngắn chỉ chứa mã khách hàng và các dòng hàng bắt buộc. Không cần đưa vào các trường response hoặc metadata mà client không gửi.

### Với persistence slice test

Một bài test dùng `@DataJpaTest` thường chuẩn bị các entity bằng repository trước khi truy vấn. Fixture phải đáp ứng các ràng buộc của entity và schema.

```java
@DataJpaTest
class ProductRepositoryTest {

    @Autowired
    private ProductRepository productRepository;

    @Test
    void findsProductBySku() {
        Product product = new Product(
                "BOOK-01",
                "Spring Testing",
                new BigDecimal("120000")
        );

        productRepository.save(product);

        Optional<Product> result =
                productRepository.findBySku("BOOK-01");

        assertTrue(result.isPresent());
        assertEquals("Spring Testing", result.orElseThrow().getName());
    }
}
```

Fixture ở đây là một sản phẩm có mã SKU, tên và giá hợp lệ. Test chỉ tạo một bản ghi vì chỉ cần một sản phẩm để xác nhận truy vấn theo SKU. Nếu truy vấn cần phân biệt hai sản phẩm, lúc đó mới tạo thêm bản ghi thứ hai để thể hiện điều kiện phân biệt.

Các test slice như `@DataJpaTest` thường chạy trong transaction do Spring Test quản lý và rollback sau mỗi test method. Điều này giúp dữ liệu của test không tích lũy giữa các method. Nếu test dùng transaction tùy chỉnh, commit, luồng bất đồng bộ hoặc tài nguyên bên ngoài, cần hiểu rõ cơ chế dọn dẹp tương ứng; không nên giả định mọi test Spring đều tự rollback dữ liệu.

### Khi fixture có nhiều bản ghi liên quan

Một tình huống truy vấn phức tạp có thể cần nhiều entity có quan hệ. Có thể tạo chúng bằng factory có tên mô tả vai trò, hoặc đặt dữ liệu trong file SQL nếu bộ dữ liệu lớn, ổn định và dễ biểu diễn bằng SQL.

Ví dụ, `@Sql` có thể nạp dữ liệu trước test từ một file script. Cách này hữu ích khi test cần một cấu trúc quan hệ cụ thể hoặc dữ liệu được chia sẻ bởi nhiều test. Tuy nhiên, file SQL cũng là một phần của fixture và cần dễ đọc, có tên gắn với tình huống, đồng thời có chiến lược dọn dữ liệu phù hợp.

Không nên nạp một bộ dữ liệu lớn cho mọi test nếu mỗi test chỉ cần một vài bản ghi. Dữ liệu thừa làm tăng thời gian chạy và khiến nguyên nhân của kết quả khó xác định.

## 9. Giữ fixture độc lập và có thể lặp lại

Một fixture tốt phải tạo ra cùng điều kiện đầu vào mỗi lần test chạy. Trạng thái dùng chung, thời gian hệ thống và dữ liệu ngẫu nhiên là những nguồn gây ra kết quả không ổn định.

### Tạo đối tượng mới cho mỗi test

Đối tượng mutable nên được tạo mới trong từng test hoặc trong `@BeforeEach`. Tránh dùng một đối tượng static rồi sửa thuộc tính của nó qua nhiều test.

### Kiểm soát thời gian

Nếu logic phụ thuộc ngày hiện tại, test không nên dựa trực tiếp vào đồng hồ máy tính. Có thể truyền `Clock` vào thành phần cần kiểm tra và dùng đồng hồ cố định trong test:

```java
Clock testClock = Clock.fixed(
        Instant.parse("2026-01-15T10:00:00Z"),
        ZoneOffset.UTC
);
```

Khi thời gian được cố định, test có thể xác định rõ ngày giờ dùng để tính hạn hoặc kiểm tra trạng thái hết hạn. Nếu thời gian không thuộc mục tiêu, không cần đưa thêm đồng hồ vào fixture.

### Kiểm soát phụ thuộc bên ngoài

Nếu bài test chỉ kiểm tra logic service, không cần gọi một dịch vụ HTTP thật. Có thể dùng mock hoặc fake để kiểm soát kết quả phụ thuộc. Nếu mục tiêu là xác nhận tích hợp HTTP hoặc database thật, fixture và môi trường phải chuẩn bị thành phần tương ứng; khi đó không nên thay thế chính thành phần mà bài test cần xác minh.

Việc chọn mock hay tài nguyên thật phụ thuộc vào câu hỏi của test. Fixture phải phản ánh đúng phạm vi bằng chứng mà bài kiểm thử muốn thu thập.

## 10. Những cách chuẩn bị dữ liệu dễ gây khó hiểu

| Cách làm | Vấn đề | Cách cải thiện |
|---|---|---|
| Tạo nhiều đối tượng không liên quan | Che khuất dữ liệu quyết định kết quả | Chỉ giữ dữ liệu cần cho tình huống |
| Helper tên chung chung như `createData()` | Người đọc phải mở helper mới biết trạng thái | Đặt tên theo vai trò hoặc trạng thái |
| Nhiều tham số boolean | Lời gọi không thể hiện ý nghĩa từng giá trị | Dùng enum, tên tham số hoặc builder rõ nghĩa |
| Fixture mutable dùng chung | Test có thể ảnh hưởng lẫn nhau | Tạo fixture mới cho mỗi test |
| Dùng thời gian hiện tại hoặc random không kiểm soát | Kết quả có thể thay đổi giữa các lần chạy | Dùng giá trị cố định hoặc seed xác định |
| Đưa toàn bộ dữ liệu vào `@BeforeEach` | Mỗi test bị che khuất bởi phần setup lớn | Để dữ liệu riêng gần test cần nó |
| Mặc định quá nhiều trường quan trọng | Điều kiện của test bị ẩn | Ghi rõ các giá trị quyết định kết quả |
| Dùng fixture không hợp lệ để vượt qua constructor | Test không phản ánh trạng thái ứng dụng có thể tạo ra | Tạo đối tượng hợp lệ qua API công khai |

Một lỗi thường gặp là tạo helper quá tổng quát để phục vụ mọi tình huống. Helper có thể nhận mười tham số, trong đó phần lớn là boolean hoặc chuỗi rỗng. Sau một thời gian, người đọc không còn hiểu mỗi lời gọi đang tạo trạng thái gì. Khi fixture có nhiều biến thể thực sự khác nhau, hãy cân nhắc các factory có tên riêng như `anActiveCustomer()`, `anExpiredSubscription()` hoặc `aDraftOrder()`.

Cũng không nên ép mọi test dùng chung một fixture chỉ vì chúng cùng kiểm tra một lớp. Hai hành vi khác nhau có thể cần những trạng thái ban đầu khác nhau. Fixture nên phục vụ mục tiêu của từng test, còn phần dùng chung chỉ nên giữ những cấu trúc thực sự giống nhau.

## 11. Cách phát triển fixture từ đơn giản đến phù hợp

Không cần thiết kế một hệ thống tạo dữ liệu trước khi viết test đầu tiên. Có thể bắt đầu từ dữ liệu trực tiếp, rồi chỉ trích xuất khi có lý do rõ ràng:

1. Viết test với dữ liệu ngay trong phần Arrange để nhìn rõ tình huống.
2. Đặt tên biến cho những giá trị quan trọng hoặc khó hiểu nếu để trực tiếp.
3. Khi nhiều test lặp lại cùng cách tạo đối tượng, trích xuất một factory có tên mô tả.
4. Khi đối tượng có nhiều thuộc tính hoặc nhiều biến thể, cân nhắc builder.
5. Khi nhiều test thực sự cần cùng phần chuẩn bị nền, đưa phần đó vào `@BeforeEach`.
6. Khi dữ liệu liên quan đến database hoặc tài nguyên ngoài, chọn cách nạp và dọn fixture phù hợp với transaction và phạm vi test.

Sau mỗi lần trích xuất, phần test nên vẫn cho thấy được điều kiện quan trọng. Nếu người đọc phải lần qua nhiều lớp helper để biết test đang dùng trạng thái nào, việc trừu tượng hóa đã đi quá xa.

Fixture tối thiểu và dễ đọc giúp một bài kiểm thử kể lại tình huống bằng dữ liệu cụ thể: hệ thống bắt đầu ở trạng thái nào, hành động nào được thực hiện và kết quả nào cần được xác nhận. Khi phần chuẩn bị rõ ràng, người đọc có thể tập trung vào hành vi cần bảo vệ và hiểu kết quả PASS hoặc FAIL trong đúng bối cảnh của nó.

