# Xác định điều kiện đầu vào và kết quả mong đợi

Khi thiết kế một bài kiểm thử, hai câu hỏi cần được trả lời rõ ràng là: **đối tượng được kiểm thử đang nhận những điều kiện đầu vào nào?** và **với những điều kiện đó, hệ thống phải tạo ra kết quả gì?** Nếu chỉ gọi một phương thức rồi kiểm tra rằng nó không phát sinh lỗi, bài kiểm thử thường chưa mô tả đủ hành vi mà ứng dụng cần bảo đảm.

Trong Spring Framework Testing, việc xác định đầu vào và kết quả mong đợi giúp ta chọn đúng cách dựng dữ liệu, cấu hình Spring context, giả lập dependency và viết assertion. Một test case tốt mô tả được hành vi quan sát được từ bên ngoài, đồng thời đủ cụ thể để khi thất bại ta biết điều kiện nào đã không được đáp ứng.

## 1. Hiểu đúng đầu vào và kết quả mong đợi

**Đầu vào** là toàn bộ dữ kiện có thể ảnh hưởng đến hành vi đang kiểm thử. Nó không chỉ là tham số truyền vào phương thức. Tùy phạm vi kiểm thử, đầu vào có thể gồm:

- Giá trị trực tiếp: chuỗi, số, đối tượng, request HTTP, message hoặc sự kiện.
- Trạng thái ban đầu: bản ghi đã tồn tại hay chưa, tài khoản đang hoạt động hay bị khóa, giỏ hàng đang rỗng hay có sản phẩm.
- Phản hồi từ dependency: repository trả về dữ liệu hay không tìm thấy dữ liệu, dịch vụ ngoài trả về thành công hay lỗi.
- Cấu hình và môi trường: property, profile, bean được chọn, múi giờ, locale hoặc quyền truy cập.
- Thời điểm và trạng thái vòng đời: dữ liệu đã hết hạn chưa, transaction đang mở hay đã kết thúc.

**Kết quả mong đợi** là hành vi có thể quan sát và kiểm chứng sau khi thực hiện thao tác. Kết quả có thể gồm nhiều phần:

- Giá trị trả về hoặc kiểu dữ liệu trả về.
- Exception được phát sinh trong trường hợp đầu vào không hợp lệ.
- HTTP status, response body, header hoặc redirect của endpoint.
- Trạng thái dữ liệu được lưu, cập nhật hoặc xóa.
- Tương tác cần thiết với dependency, chẳng hạn chỉ lưu một lần hoặc không gọi dịch vụ ngoài khi dữ liệu không hợp lệ.
- Sự kiện được phát ra, transaction được commit/rollback hoặc một thay đổi trạng thái khác thuộc hợp đồng của chức năng.

Không phải test case nào cũng cần kiểm tra tất cả các loại kết quả trên. Hãy chọn những kết quả có ý nghĩa đối với hành vi đang kiểm thử.

### Phân biệt đầu vào, điều kiện trước và kết quả

Ba khái niệm này liên quan với nhau nhưng trả lời các câu hỏi khác nhau:

| Thành phần | Câu hỏi cần trả lời | Ví dụ đăng ký tài khoản |
|---|---|---|
| Đầu vào | Người dùng hoặc caller cung cấp gì? | Email, mật khẩu |
| Điều kiện trước | Trạng thái nào đã tồn tại trước khi hành động bắt đầu? | Email chưa được sử dụng; repository đang chứa một tài khoản trùng email |
| Phản hồi dependency | Thành phần cộng tác phản hồi thế nào trong phạm vi test? | `existsByEmail` trả về `true` hoặc `false` |
| Kết quả mong đợi | Hành động phải trả về hoặc phát sinh điều gì? | Tạo tài khoản hoặc phát sinh `DuplicateEmailException` |
| Tác động phụ | Hệ thống được phép thay đổi điều gì? | Lưu tài khoản đúng một lần; không lưu khi email đã tồn tại |

Ví dụ, câu “đầu vào là email hợp lệ” chưa đủ để mô tả một test case đăng ký. Ta còn cần biết email đó đã tồn tại hay chưa, mật khẩu có đạt độ dài tối thiểu không, và khi đăng ký thành công thì tài khoản được lưu với email đã chuẩn hóa hay không.

## 2. Bắt đầu từ hợp đồng của hành vi

Trước khi viết test, hãy diễn đạt hành vi cần bảo vệ bằng một câu có điều kiện và kết quả:

> Khi **điều kiện đầu vào và trạng thái ban đầu** là ..., nếu thực hiện **hành động** ..., hệ thống phải **tạo ra kết quả quan sát được** ... .

Ví dụ:

> Khi email chưa được sử dụng và mật khẩu đáp ứng độ dài tối thiểu, nếu người dùng đăng ký bằng email có khoảng trắng ở hai đầu và chữ hoa, hệ thống tạo tài khoản với email đã được chuẩn hóa và lưu mật khẩu đã mã hóa.

Câu mô tả này cho biết cần chuẩn bị một email chưa tồn tại, cung cấp mật khẩu hợp lệ, gọi hành vi đăng ký và kiểm tra cả dữ liệu kết quả lẫn thao tác lưu. Nó cũng giúp tránh viết một test chỉ kiểm tra rằng phương thức trả về một đối tượng khác `null`.

Có thể xác định hợp đồng theo trình tự sau:

1. **Chọn hành vi cần kiểm thử.** Xác định phương thức, use case, endpoint hoặc luồng xử lý mà người dùng hay thành phần khác có thể quan sát.
2. **Liệt kê dữ liệu đầu vào.** Ghi nhận tham số, request field, header, message và các giá trị cấu hình có ảnh hưởng trực tiếp.
3. **Xác định trạng thái ban đầu.** Nêu rõ dữ liệu cần có hoặc không được có trước khi hành động chạy.
4. **Xác định phản hồi từ dependency.** Nếu kết quả phụ thuộc repository, gateway hoặc dịch vụ khác, chỉ rõ dependency sẽ phản hồi gì trong test.
5. **Viết kết quả mong đợi.** Dùng giá trị, trạng thái, exception hoặc tương tác cụ thể có thể kiểm chứng.
6. **Xác định điều không được xảy ra.** Ví dụ: không lưu dữ liệu khi validation thất bại, không gửi email khi giao dịch bị từ chối.

Việc ghi rõ cả điều phải xảy ra và điều không được xảy ra giúp phát hiện những lỗi tác động phụ. Một thao tác có thể trả về đúng exception nhưng vẫn ghi dữ liệu sai trước khi phát sinh exception; chỉ kiểm tra exception sẽ bỏ sót lỗi đó.

## 3. Chia miền đầu vào thành các trường hợp có ý nghĩa

Không nên chỉ chọn một bộ dữ liệu “bình thường” rồi xem đó là đủ. Hãy phân loại các giá trị theo cách chúng ảnh hưởng đến hành vi.

### 3.1. Phân vùng tương đương

Phân vùng tương đương là cách chia miền đầu vào thành các nhóm mà các giá trị trong cùng nhóm được kỳ vọng xử lý giống nhau. Ta thường chọn một hoặc một vài đại diện cho mỗi nhóm thay vì thử mọi giá trị có thể có.

Ví dụ, chức năng đăng ký yêu cầu mật khẩu có ít nhất 12 ký tự:

| Nhóm đầu vào | Giá trị đại diện | Kết quả cần kiểm tra |
|---|---|---|
| Thiếu mật khẩu | `null` hoặc chuỗi rỗng | Từ chối đầu vào |
| Ngắn hơn giới hạn | 11 ký tự | Từ chối đầu vào |
| Đúng giới hạn | 12 ký tự | Chấp nhận nếu các điều kiện khác hợp lệ |
| Dài hơn giới hạn | 13 ký tự | Chấp nhận nếu các điều kiện khác hợp lệ |

Nếu quy tắc nghiệp vụ chỉ phân biệt mật khẩu dưới 12 ký tự và từ 12 ký tự trở lên, không cần tạo hàng chục test cho các độ dài 13, 14, 15... Một số giá trị đại diện đủ chứng minh các nhóm quan trọng.

### 3.2. Kiểm thử giá trị biên

Lỗi thường xuất hiện tại điểm chuyển giữa hợp lệ và không hợp lệ. Với giới hạn tối thiểu là 12, các giá trị đáng chú ý là 11, 12 và 13. Với giới hạn tối đa là 100, hãy chú ý 99, 100 và 101.

Giá trị biên cũng áp dụng cho:

- Số lượng phần tử trong danh sách: 0, 1 và giới hạn cho phép.
- Ngày giờ: ngay trước, đúng tại và ngay sau thời điểm hết hạn.
- Số tiền: 0, số tiền nhỏ nhất, ngưỡng miễn phí vận chuyển hoặc ngưỡng áp dụng chiết khấu.
- Phân trang: trang đầu, trang cuối, kích thước trang bằng 0 hoặc vượt giới hạn.

Hãy phân biệt rõ quy tắc nghiệp vụ. Chẳng hạn, “ít nhất 12 ký tự” bao gồm giá trị 12; “nhiều hơn 12 ký tự” thì không bao gồm giá trị đó. Test ở đúng biên sẽ giúp phát hiện lỗi dùng nhầm `>` với `>=`.

### 3.3. Bảng quyết định cho nhiều điều kiện

Khi kết quả phụ thuộc đồng thời vào nhiều điều kiện, bảng quyết định giúp nhìn thấy các tổ hợp quan trọng. Ví dụ, một đơn hàng chỉ được xác nhận khi tồn kho đủ và thanh toán thành công:

| Tồn kho đủ | Thanh toán thành công | Kết quả mong đợi |
|---|---|---|
| Có | Có | Xác nhận đơn hàng |
| Có | Không | Từ chối xác nhận, giữ trạng thái chưa thanh toán |
| Không | Có | Không xác nhận; xử lý hoàn tiền hoặc giữ khoản thanh toán theo hợp đồng đã định nghĩa |
| Không | Không | Từ chối xác nhận |

Hàng thứ ba cho thấy vì sao cần xác định kết quả đầy đủ: “đơn hàng không được xác nhận” có thể chưa đủ nếu hệ thống đã thu tiền. Tác động lên thanh toán phải được quy định rõ trong hợp đồng chức năng trước khi viết assertion.

### 3.4. Kiểm thử trạng thái và chuyển trạng thái

Với đối tượng có vòng đời, đầu vào còn bao gồm trạng thái hiện tại. Một yêu cầu hủy đơn hàng có thể hợp lệ khi đơn ở trạng thái `PENDING`, nhưng không hợp lệ khi đơn đã `SHIPPED` hoặc `CANCELLED`.

Hãy ghi rõ cặp **trạng thái ban đầu → hành động → trạng thái sau cùng**. Nếu có nhiều trạng thái, kiểm tra các chuyển đổi được phép và các chuyển đổi phải bị từ chối. Cách này hữu ích với workflow, đơn hàng, phiên đăng nhập, quy trình phê duyệt và các entity có state machine.

### 3.5. Tránh tạo mọi tổ hợp một cách máy móc

Nếu một chức năng có nhiều trường đầu vào, tích Descartes của mọi giá trị có thể tạo ra số lượng test rất lớn. Không phải mọi tổ hợp đều có giá trị như nhau.

- Ưu tiên tổ hợp đại diện cho từng quy tắc nghiệp vụ và từng nhánh quyết định.
- Kiểm tra riêng các điều kiện có thể che khuất nhau, ví dụ email trống và mật khẩu quá ngắn.
- Kiểm tra các tương tác có rủi ro cao, ví dụ người dùng bị khóa nhưng request vẫn có token hợp lệ.
- Khi có nhiều tham số độc lập, có thể dùng kỹ thuật pairwise để chọn tập tổ hợp bao phủ các cặp giá trị; vẫn phải bổ sung các tổ hợp được quy tắc nghiệp vụ yêu cầu.

Mục tiêu là bao phủ các hành vi có ý nghĩa, không phải tăng số lượng test bằng mọi giá.

## 4. Xác định kết quả mong đợi đủ cụ thể

Một kết quả như “xử lý thành công” hoặc “trả về lỗi” quá mơ hồ. Hãy chỉ rõ điều gì chứng minh thành công hoặc lỗi đó.

| Loại hành vi | Assertion có thể cần |
|---|---|
| Hàm tính toán | Giá trị trả về chính xác, đơn vị và quy tắc làm tròn |
| Validation | Exception hoặc lỗi validation đúng loại; dữ liệu không bị ghi |
| Tìm kiếm | Số phần tử, nội dung, thứ tự và cách xử lý khi không có kết quả |
| Ghi dữ liệu | Bản ghi được tạo/cập nhật với các trường đúng; không tạo bản ghi trùng |
| Giao tiếp HTTP | Status, header, body, kiểu nội dung và cấu trúc lỗi |
| Tương tác dependency | Dependency được gọi với tham số đúng, đúng số lần khi tương tác là một phần hợp đồng |
| Giao dịch | Dữ liệu được commit hoặc rollback theo hành vi được yêu cầu |
| Sự kiện | Sự kiện cần thiết được phát ra với dữ liệu phù hợp |

Hãy ưu tiên kiểm tra kết quả quan sát được. Nếu hợp đồng chỉ yêu cầu tài khoản được lưu đúng, việc kiểm tra một phương thức private đã được gọi có thể làm test phụ thuộc vào cách cài đặt. Ngược lại, nếu hợp đồng quy định một email chỉ được gửi một lần, số lần gọi cổng gửi email là điều đáng kiểm tra.

Với trường hợp lỗi, hãy xác định cả:

- Loại lỗi hoặc HTTP status cần trả về.
- Mã lỗi hoặc thông tin lỗi ổn định mà client dựa vào, nếu có.
- Trạng thái dữ liệu sau khi lỗi xảy ra.
- Các tác động phụ cần bị ngăn chặn.

Không nên khóa test vào toàn bộ chuỗi thông báo lỗi nếu nội dung đó không phải hợp đồng công khai. Thông báo có thể được biên tập lại mà không làm thay đổi hành vi. Hãy kiểm tra loại exception, mã lỗi hoặc trường response ổn định theo yêu cầu của ứng dụng.

## 5. Áp dụng khi kiểm thử ứng dụng Spring

Spring cung cấp nhiều cách tạo điều kiện kiểm thử. Cách chọn phụ thuộc vào phạm vi hành vi cần xác minh.

### 5.1. Unit test cho logic độc lập

Nếu cần kiểm tra quy tắc trong một service mà không cần Spring container, hãy dùng JUnit và mock các dependency bên ngoài. Cách này giúp kiểm soát chính xác phản hồi của repository hoặc gateway, đồng thời test chạy nhanh.

Ví dụ, giả sử `RegistrationService` có hợp đồng:

- Từ chối email rỗng.
- Yêu cầu mật khẩu ít nhất 12 ký tự.
- Chuẩn hóa email bằng cách bỏ khoảng trắng ở hai đầu và chuyển thành chữ thường.
- Từ chối email đã tồn tại.
- Mã hóa mật khẩu trước khi lưu tài khoản.

Một ma trận test case có thể được lập trước khi viết code:

| Trường hợp | Đầu vào và trạng thái ban đầu | Kết quả mong đợi |
|---|---|---|
| Email rỗng | Email chỉ chứa khoảng trắng | `IllegalArgumentException`; không truy cập repository và encoder |
| Mật khẩu quá ngắn | Email hợp lệ, mật khẩu 11 ký tự | `IllegalArgumentException`; không lưu tài khoản |
| Email đã tồn tại | Email sau chuẩn hóa đã có trong repository | `DuplicateEmailException`; không mã hóa và không lưu |
| Đăng ký hợp lệ | Email chưa tồn tại, mật khẩu đủ dài | Trả về tài khoản đã lưu với email chuẩn hóa và mật khẩu đã mã hóa |
| Đúng giới hạn mật khẩu | Mật khẩu có đúng 12 ký tự | Được chấp nhận nếu các điều kiện khác hợp lệ |

Ví dụ kiểm thử bằng JUnit 5 và Mockito:

```java
@ExtendWith(MockitoExtension.class)
class RegistrationServiceTest {

    @Mock
    private AccountRepository repository;

    @Mock
    private PasswordEncoder passwordEncoder;

    @InjectMocks
    private RegistrationService service;

    @Test
    void rejectsBlankEmailBeforeCallingDependencies() {
        assertThrows(IllegalArgumentException.class,
                () -> service.register("   ", "valid-password-123"));

        verifyNoInteractions(repository, passwordEncoder);
    }

    @Test
    void rejectsDuplicateEmailWithoutEncodingOrSaving() {
        when(repository.existsByEmail("user@example.com")).thenReturn(true);

        assertThrows(DuplicateEmailException.class,
                () -> service.register(" USER@example.com ", "valid-password-123"));

        verify(repository).existsByEmail("user@example.com");
        verifyNoMoreInteractions(repository);
        verifyNoInteractions(passwordEncoder);
    }

    @Test
    void normalizesEmailAndSavesEncodedPassword() {
        when(repository.existsByEmail("user@example.com")).thenReturn(false);
        when(passwordEncoder.encode("valid-password-123"))
                .thenReturn("encoded-value");
        when(repository.save(any(Account.class)))
                .thenAnswer(invocation -> invocation.getArgument(0));

        Account result = service.register(
                " USER@example.com ", "valid-password-123");

        assertEquals("user@example.com", result.email());
        assertEquals("encoded-value", result.passwordHash());

        ArgumentCaptor<Account> captor = ArgumentCaptor.forClass(Account.class);
        verify(repository).save(captor.capture());
        assertEquals("user@example.com", captor.getValue().email());
        assertEquals("encoded-value", captor.getValue().passwordHash());
    }
}
```

Đoạn mã minh họa giả định `Account` là một record có hai accessor `email()` và `passwordHash()`, `AccountRepository` có `existsByEmail` và `save`, còn `RegistrationService` thực hiện đúng hợp đồng đã nêu. Tên lớp và API cụ thể cần khớp với ứng dụng thực tế.

Test thứ nhất kiểm tra đầu vào không hợp lệ và xác nhận không dependency nào bị gọi. Test thứ hai dựng trạng thái “email đã tồn tại”, sau đó kiểm tra exception và ngăn thao tác mã hóa/lưu. Test thứ ba dựng phản hồi của các dependency để xác minh dữ liệu được chuẩn hóa và lưu. Như vậy mỗi test có một mục đích rõ ràng và kiểm tra cả kết quả lẫn tác động phụ liên quan.

Có thể kiểm tra biên độ dài bằng test tham số:

```java
@ParameterizedTest
@ValueSource(strings = {"", "12345678901"})
void rejectsPasswordShorterThanTwelveCharacters(String password) {
    assertThrows(IllegalArgumentException.class,
            () -> service.register("user@example.com", password));

    verifyNoInteractions(repository, passwordEncoder);
}
```

Trong test thực tế, nên bổ sung trường hợp đúng 12 ký tự để xác nhận ranh giới được chấp nhận. Nếu muốn bao gồm `null`, có thể dùng `@NullSource` cùng với `@MethodSource` hoặc một test riêng phù hợp với chữ ký phương thức.

### 5.2. Khi cần Spring TestContext

Khi hành vi phụ thuộc vào việc Spring tạo bean, inject dependency, áp dụng profile, xử lý transaction hoặc cấu hình application context, hãy kiểm thử trong Spring TestContext.

Với JUnit Jupiter, `SpringExtension` tích hợp vòng đời test của JUnit với Spring TestContext Framework. `@ContextConfiguration` chỉ định cấu hình cần nạp:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestApplicationConfig.class)
class RegistrationServiceContextTest {

    @Autowired
    private RegistrationService service;

    @Test
    void serviceIsCreatedWithRequiredDependencies() {
        assertNotNull(service);
    }
}
```

Ví dụ trên chỉ minh họa cách nạp context và inject bean. Nếu mục tiêu là xác minh quy tắc đăng ký, test cần chuẩn bị dependency và dữ liệu phù hợp rồi kiểm tra kết quả nghiệp vụ; chỉ kiểm tra bean khác `null` chưa chứng minh quy tắc đó đúng.

Chọn cấu hình kiểm thử vừa đủ:

- Dùng unit test khi chỉ cần kiểm tra logic của một lớp.
- Dùng Spring TestContext khi cần xác minh wiring, bean lifecycle, profile, property hoặc transaction do Spring quản lý.
- Dùng test slice khi chỉ cần một phần hạ tầng, chẳng hạn lớp web hoặc persistence trong ứng dụng Spring Boot.
- Dùng `@SpringBootTest` khi cần kiểm tra nhiều thành phần được cấu hình cùng nhau ở phạm vi ứng dụng; tránh dùng nó mặc định cho mọi quy tắc nhỏ.

Các annotation test của Spring Boot như `@WebMvcTest` và `@DataJpaTest` là lựa chọn theo slice của Spring Boot. Với Spring MVC Test thuần, có thể dựng `MockMvc` từ controller bằng `MockMvcBuilders` mà không cần khởi động toàn bộ ứng dụng.

### 5.3. Kiểm thử tầng web với MockMvc

Với endpoint HTTP, hãy xem request là đầu vào gồm method, path, query parameter, header, content type, body và trạng thái xác thực. Kết quả mong đợi nên nêu rõ status, response body và header quan trọng.

Ví dụ một hợp đồng giả định cho endpoint tạo tài khoản:

```java
mockMvc.perform(post("/accounts")
        .contentType(MediaType.APPLICATION_JSON)
        .content("""
                {
                  "email": "user@example.com",
                  "password": "valid-password-123"
                }
                """))
    .andExpect(status().isCreated())
    .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
    .andExpect(jsonPath("$.email").value("user@example.com"));
```

Đây là ví dụ về cách thể hiện assertion, không phải quy ước bắt buộc cho mọi API. Nếu hợp đồng của ứng dụng yêu cầu `201 Created`, header `Location` hoặc một response DTO cụ thể, hãy kiểm tra các phần đó. Với request không hợp lệ, hãy kiểm tra status và cấu trúc lỗi mà API công bố, đồng thời xác minh không có dữ liệu được ghi ngoài ý muốn.

### 5.4. Kiểm thử persistence và transaction

Khi cần xác minh truy vấn hoặc ánh xạ dữ liệu, hãy sử dụng persistence test với cơ sở dữ liệu phù hợp. Mock repository chỉ xác minh cách service tương tác với repository; nó không chứng minh câu SQL, mapping hoặc ràng buộc cơ sở dữ liệu hoạt động đúng.

Trong test có transaction do Spring quản lý, dữ liệu thường được rollback sau mỗi test theo cấu hình mặc định của Spring TestContext. Tuy nhiên, không nên giả định mọi tác động đều tự động rollback: thao tác chạy ở thread khác, transaction độc lập như `REQUIRES_NEW`, message gửi ra ngoài hoặc lời gọi HTTP không nằm trong transaction test hiện tại. Hãy thiết kế điều kiện và cách dọn dữ liệu tương ứng với ranh giới transaction thật.

## 6. Chuẩn bị dependency để điều kiện kiểm thử có thể kiểm soát

Khi kết quả phụ thuộc vào thành phần khác, hãy xác định phản hồi dependency là một phần của điều kiện test. Với unit test, Mockito có thể mô phỏng các phản hồi đó. Với integration test, nên dùng thành phần thật hoặc một test double phù hợp với mục tiêu.

Ví dụ, nếu kiểm thử service xử lý đơn hàng:

- Repository trả về đơn hàng đang ở trạng thái `PENDING`.
- Cổng thanh toán trả về kết quả thành công.
- Dịch vụ tồn kho xác nhận đủ số lượng.
- Kết quả mong đợi là đơn hàng chuyển sang `CONFIRMED` và phát sự kiện xác nhận theo hợp đồng.

Một test khác có thể dựng cổng thanh toán trả về thất bại. Khi đó cần nêu rõ đơn hàng giữ trạng thái nào, có phát sự kiện hay không và có gọi dịch vụ giao hàng hay không.

Không nên để mock trả về giá trị mặc định ngoài ý muốn. Với mỗi dependency ảnh hưởng đến kết quả, hãy cấu hình phản hồi rõ ràng để người đọc hiểu test đang mô phỏng trạng thái nào. Đồng thời chỉ mock dependency nằm ngoài phạm vi hành vi cần kiểm tra; nếu mock chính thành phần đang muốn xác minh, test sẽ không còn kiểm tra được hành vi thật.

## 7. Tổ chức test case dễ đọc và dễ bảo trì

Một test case nên có cấu trúc rõ ràng:

1. **Arrange:** tạo dữ liệu, trạng thái ban đầu, cấu hình và phản hồi dependency.
2. **Act:** thực hiện đúng một hành động chính.
3. **Assert:** kiểm tra kết quả và tác động phụ quan trọng.

Tên test có thể mô tả hành vi theo mẫu `method_condition_expectedOutcome`, ví dụ:

```java
@Test
void cancel_whenOrderIsAlreadyShipped_throwsInvalidStateException() {
    // Arrange: đơn hàng đang ở trạng thái SHIPPED
    // Act: yêu cầu hủy đơn hàng
    // Assert: thao tác bị từ chối và trạng thái không đổi
}
```

Tên test nên nói rõ điều kiện và kết quả, tránh các tên chung chung như `test1`, `testSuccess` hoặc `shouldWork`.

Khi có nhiều trường hợp cùng một quy tắc, `@ParameterizedTest` giúp dùng chung phần thực thi và thể hiện rõ dữ liệu đầu vào. Khi các trường hợp có cách chuẩn bị hoặc assertion khác nhau đáng kể, các test riêng thường dễ đọc hơn một test lớn chứa nhiều nhánh `if`.

Có thể ghi test case trước khi viết mã bằng mẫu sau:

| Trường thông tin | Nội dung cần ghi |
|---|---|
| Tên test | Điều kiện và kết quả chính |
| Hành vi | Phương thức, use case hoặc endpoint được kiểm thử |
| Điều kiện trước | Trạng thái dữ liệu và môi trường ban đầu |
| Đầu vào | Tham số, request, header hoặc message |
| Dependency | Phản hồi cần thiết từ repository, gateway hoặc dịch vụ khác |
| Kết quả | Giá trị trả về, exception, HTTP response hoặc trạng thái mới |
| Tác động phụ | Những lời gọi, bản ghi hoặc sự kiện được phép/không được phép |
| Dọn dẹp | Cách khôi phục dữ liệu hoặc tài nguyên sau test nếu cần |

## 8. Giữ test ổn định và độc lập

Điều kiện đầu vào cần được dựng rõ ràng để test có thể chạy lặp lại với cùng kết quả. Một số nguyên nhân thường làm test thiếu ổn định:

- Phụ thuộc vào ngày giờ hiện tại. Hãy truyền `Clock` hoặc nguồn thời gian có thể kiểm soát và cố định thời điểm trong test.
- Phụ thuộc vào dữ liệu do test trước tạo ra. Mỗi test cần tự chuẩn bị trạng thái của nó hoặc dùng cơ chế fixture có kiểm soát.
- Dùng dữ liệu ngẫu nhiên mà không cố định seed hoặc không ghi lại giá trị khi thất bại.
- Gọi dịch vụ bên ngoài thật trong unit test, khiến kết quả phụ thuộc mạng, credential hoặc trạng thái hệ thống khác.
- Dùng chung mutable object giữa nhiều test, làm thay đổi thứ tự chạy dẫn đến kết quả khác nhau.
- Chỉ kiểm tra response mà không kiểm tra trạng thái lưu, khiến lỗi dữ liệu bị bỏ qua.

Với test tích hợp, hãy xác định rõ dữ liệu cần được tạo ở đâu, được cô lập bằng transaction hay schema riêng, và được dọn dẹp thế nào. Test không nên phụ thuộc vào thứ tự thực thi hoặc dữ liệu còn sót từ một lần chạy trước.

## 9. Những lỗi thiết kế thường gặp

**Chỉ kiểm tra trường hợp thành công.** Một chức năng thường có nhiều nhánh từ chối, dữ liệu biên và trạng thái bất thường. Hãy phân vùng đầu vào và chọn các trường hợp đại diện cho quy tắc quan trọng.

**Không ghi trạng thái ban đầu.** “Gửi request hủy đơn hàng” chưa đủ; kết quả có thể khác nhau tùy đơn hàng đang `PENDING`, `SHIPPED` hay `CANCELLED`.

**Kết quả mong đợi quá chung chung.** Assertion `assertNotNull(result)` không cho biết nội dung, trạng thái hay tác động phụ có đúng không. Hãy kiểm tra các thuộc tính quan trọng theo hợp đồng.

**Gộp nhiều hành vi độc lập vào một test.** Khi một test vừa đăng ký tài khoản, gửi email, đăng nhập và cập nhật hồ sơ, lỗi ở bước nào cũng làm test thất bại. Tách test theo hành vi hoặc theo luồng tích hợp thực sự cần xác minh.

**Kiểm tra quá sâu chi tiết cài đặt.** Xác minh mọi lời gọi nội bộ có thể khiến test hỏng khi refactor dù hành vi bên ngoài không đổi. Chỉ kiểm tra tương tác khi nó là một phần hợp đồng hoặc cần thiết để chứng minh tác động phụ.

**Mock toàn bộ hệ thống.** Nếu mọi thành phần đều là mock, test chỉ chứng minh các mock đã được cấu hình và gọi theo kịch bản. Hãy chọn đúng ranh giới: unit test mock dependency; integration test giữ lại những thành phần cần được xác minh cùng nhau.

**Không kiểm tra điều không được phép xảy ra.** Trong trường hợp lỗi, ngoài assertion về exception hoặc HTTP status, hãy xác minh không có bản ghi, thanh toán hoặc sự kiện không mong muốn.

**Dùng Spring context quá rộng cho một quy tắc nhỏ.** Khởi động toàn bộ ứng dụng làm test chậm và tăng số yếu tố ảnh hưởng. Chỉ nạp context khi hành vi cần kiểm tra thực sự phụ thuộc cấu hình hoặc tích hợp của Spring.

## 10. Quy trình hoàn thiện một bộ điều kiện và kết quả

Trước khi triển khai test, hãy tự trả lời các câu hỏi sau:

- Hành vi nào đang được bảo vệ và ai quan sát được hành vi đó?
- Những tham số, trạng thái, cấu hình và phản hồi dependency nào có thể làm thay đổi kết quả?
- Miền đầu vào có những nhóm hợp lệ, không hợp lệ và giá trị biên nào?
- Có những trạng thái ban đầu nào dẫn đến kết quả khác nhau?
- Kết quả cần kiểm tra là giá trị trả về, exception, response, dữ liệu lưu hay tác động phụ nào?
- Khi thao tác thất bại, những thay đổi nào bắt buộc không được xảy ra?
- Phạm vi kiểm thử phù hợp là unit test, Spring TestContext, MVC test hay persistence integration test?
- Dữ liệu và dependency đã được chuẩn bị đủ rõ để test chạy độc lập, lặp lại chưa?

Khi câu trả lời cho các câu hỏi này được thể hiện trong test case, phần Arrange sẽ có dữ liệu và trạng thái xác định; phần Act sẽ tập trung vào hành động cần kiểm tra; phần Assert sẽ xác minh những kết quả cụ thể. Nhờ vậy, mỗi test trở thành một ví dụ có thể đọc được về hợp đồng của ứng dụng Spring, đồng thời giúp phát hiện chính xác điều kiện nào làm hành vi sai lệch.
