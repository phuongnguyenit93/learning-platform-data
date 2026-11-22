# Chọn một hành vi có thể quan sát làm mục tiêu

Thiết kế một bài kiểm thử tốt bắt đầu bằng việc xác định **hệ thống phải làm gì mà người sử dụng hoặc thành phần gọi nó có thể nhận biết được**. Mục tiêu của bài kiểm thử là hành vi đó, chứ không phải tên một phương thức, số dòng code hay cách lập trình viên hiện thực hóa nó.

Trong ứng dụng Spring, một hành vi có thể xuất hiện ở nhiều ranh giới: một HTTP endpoint trả về phản hồi, một service áp dụng quy tắc nghiệp vụ, một repository lưu và truy vấn dữ liệu, một listener xử lý sự kiện, hoặc một thành phần gọi dịch vụ bên ngoài. Chọn đúng hành vi và ranh giới quan sát giúp bài kiểm thử có ý nghĩa với người dùng hệ thống, đồng thời ít bị ảnh hưởng khi cấu trúc nội bộ thay đổi.

## 1. Hành vi có thể quan sát là gì?

Một hành vi có thể quan sát là phản ứng của hệ thống trước một điều kiện và một tác động cụ thể. Phản ứng ấy có thể được xác nhận từ bên ngoài ranh giới đang kiểm thử.

Ví dụ, yêu cầu “khách hàng tạo đơn hàng hợp lệ” còn khá rộng. Có thể diễn đạt thành hành vi rõ ràng hơn:

> Khi khách hàng gửi yêu cầu tạo đơn hàng với dữ liệu hợp lệ, API trả về HTTP 201, cung cấp mã đơn hàng mới và đơn hàng được tạo ở trạng thái PENDING.

Hành vi này cho biết:

- **Điều kiện ban đầu:** yêu cầu có dữ liệu hợp lệ.
- **Tác động:** khách hàng gửi yêu cầu tạo đơn hàng.
- **Kết quả quan sát được:** phản hồi HTTP 201 và mã đơn hàng.
- **Thay đổi trạng thái được yêu cầu:** đơn hàng mới có trạng thái PENDING.

Một hành vi có thể có nhiều bằng chứng quan sát. Bài kiểm thử có thể cần kiểm tra cả status code, response body và trạng thái dữ liệu vì chúng cùng xác nhận một kết quả nghiệp vụ. Điều quan trọng là các khẳng định phải phục vụ cùng một mục tiêu.

### Những dạng kết quả có thể quan sát

| Dạng kết quả | Ví dụ trong ứng dụng Spring | Cách quan sát |
|---|---|---|
| Giá trị trả về | Service tính tổng tiền đơn hàng | Kiểm tra giá trị trả về |
| Phản hồi giao thức | Controller xử lý POST /orders | Kiểm tra HTTP status, header và JSON body bằng MockMvc |
| Trạng thái dữ liệu | Đơn hàng mới được lưu với trạng thái PENDING | Truy vấn repository hoặc cơ sở dữ liệu sau thao tác |
| Tác động bên ngoài | Hệ thống gửi yêu cầu thanh toán hoặc phát sự kiện | Quan sát gateway giả, message broker thử nghiệm hoặc hệ thống nhận sự kiện |
| Kết quả lỗi | Người dùng không có quyền truy cập tài nguyên | Kiểm tra HTTP 403 và xác nhận dữ liệu không bị thay đổi |

Không phải chi tiết nào có thể nhìn thấy trong lúc chạy chương trình cũng là kết quả phù hợp để kiểm thử. Log nội bộ, tên biến, tên phương thức private, số lần gọi một phương thức helper hay thứ tự các bước xử lý thường là chi tiết triển khai. Chỉ đưa chúng thành mục tiêu khi chúng thuộc một cam kết có ý nghĩa đối với người dùng hoặc thành phần tích hợp.

## 2. Diễn đạt mục tiêu bằng điều kiện, tác động và kết quả

Một mẫu diễn đạt hữu ích là:

**Khi** [điều kiện ban đầu], **và khi** [tác nhân thực hiện hành động], **thì** [kết quả có thể quan sát] phải xảy ra.

Ví dụ:

- Khi tài khoản đang bị khóa và người dùng gửi yêu cầu đăng nhập, hệ thống từ chối đăng nhập và trả về lỗi phù hợp.
- Khi giỏ hàng có ít nhất một sản phẩm còn hàng và khách hàng xác nhận đặt hàng, hệ thống tạo đơn hàng ở trạng thái chờ thanh toán.
- Khi repository được yêu cầu tìm khách hàng theo email không phân biệt chữ hoa chữ thường, kết quả trả về khách hàng có email tương ứng.
- Khi người dùng chưa đăng nhập truy cập tài nguyên yêu cầu xác thực, ứng dụng từ chối yêu cầu theo chính sách bảo mật.

Mục tiêu cần đủ cụ thể để người viết test có thể xác định dữ liệu đầu vào và kết quả mong đợi mà không phải tự đoán quy tắc nghiệp vụ.

### Xác định ai đang quan sát hành vi

Hãy xác định thành phần nào đang sử dụng kết quả:

- **Người dùng hoặc API client** quan sát status code, header, nội dung phản hồi và lỗi hiển thị.
- **Service gọi một service khác** quan sát giá trị trả về hoặc lỗi từ dependency.
- **Thành phần truy cập dữ liệu** quan sát bản ghi được lưu, cập nhật, xóa hoặc truy vấn.
- **Hệ thống tích hợp** quan sát sự kiện, thông điệp hoặc yêu cầu gửi đến dịch vụ bên ngoài.
- **Quản trị viên hoặc hệ thống vận hành** có thể quan sát metric, trạng thái health hoặc log khi đó là yêu cầu vận hành được công bố.

Xác định người quan sát giúp chọn đúng ranh giới kiểm thử. Chẳng hạn, client REST không quan tâm controller gọi private method nào. Client quan tâm phản hồi HTTP và kết quả nghiệp vụ mà API cam kết.

### Phân biệt hành vi với cách triển khai

Hai cách mô tả sau không có cùng chất lượng:

| Mô tả dựa trên triển khai | Mô tả dựa trên hành vi |
|---|---|
| Kiểm tra phương thức createOrder gọi repository.save | Khi yêu cầu hợp lệ được chấp nhận, một đơn hàng mới được tạo và có thể truy vấn bằng mã đơn hàng |
| Kiểm tra controller gọi service đúng một lần | Khi client gửi yêu cầu hợp lệ, endpoint trả về phản hồi thành công theo hợp đồng API |
| Kiểm tra phương thức private calculateFee trả về 10 | Khi đơn hàng thuộc khu vực giao hàng tiêu chuẩn và không đủ điều kiện miễn phí, phí giao hàng được tính theo biểu phí tiêu chuẩn |
| Kiểm tra listener gọi một helper cụ thể | Khi nhận sự kiện đơn hàng đã thanh toán, hệ thống cập nhật trạng thái đơn hàng theo quy tắc đã công bố |

Mô tả bên phải vẫn có thể được kiểm thử bằng cách quan sát tương tác nội bộ nếu tương tác đó chính là hợp đồng giữa hai thành phần. Tuy nhiên, điểm xuất phát luôn là kết quả mà hệ thống cần bảo đảm.

## 3. Quy trình chọn một hành vi làm mục tiêu

### Bước 1: Tìm yêu cầu hoặc quy tắc có ý nghĩa

Bắt đầu từ user story, tiêu chí chấp nhận, quy tắc nghiệp vụ, hợp đồng API hoặc yêu cầu tích hợp. Tìm một câu mô tả điều hệ thống phải bảo đảm.

Ví dụ yêu cầu: “Chỉ người dùng đã xác thực và có quyền ADMIN mới được xem danh sách tài khoản.”

Đây là một quy tắc có thể kiểm thử. Không cần bắt đầu bằng việc tìm controller hoặc phương thức security trong code.

### Bước 2: Chọn ranh giới quan sát

Xác định nơi kết quả trở nên có ý nghĩa đối với thành phần sử dụng:

- Với API, ranh giới thường là HTTP request/response.
- Với quy tắc nghiệp vụ, ranh giới có thể là public method của service.
- Với truy vấn dữ liệu, ranh giới thường là interface repository.
- Với xử lý sự kiện, ranh giới có thể là sự kiện đầu vào và trạng thái hoặc thông điệp đầu ra.

Ranh giới cần đủ gần yêu cầu để kiểm tra đúng cam kết, nhưng không nên mở rộng sang toàn bộ ứng dụng nếu mục tiêu chỉ thuộc một thành phần.

### Bước 3: Mô tả trạng thái ban đầu

Nêu dữ liệu và điều kiện cần có trước khi hành động diễn ra. Chỉ đưa vào những điều kiện có ảnh hưởng đến kết quả.

Ví dụ:

- Tài khoản tồn tại, đang hoạt động và có vai trò ADMIN.
- Kho còn đủ số lượng của sản phẩm được đặt.
- Email chưa được đăng ký.
- Đơn hàng đang ở trạng thái PENDING.

Nếu trạng thái ban đầu không rõ, cùng một hành động có thể dẫn đến nhiều kết quả và mục tiêu kiểm thử sẽ mơ hồ.

### Bước 4: Xác định tác động kích hoạt

Ghi rõ hành động làm hệ thống phản ứng: gọi endpoint, gọi public service method, lưu entity, phát sự kiện hoặc chạy tác vụ định kỳ.

Tránh mô tả tác động bằng một bước triển khai nội bộ như “gọi helper A rồi gọi helper B”. Người kiểm thử cần biết điều gì kích hoạt hành vi từ góc nhìn của thành phần sử dụng.

### Bước 5: Chọn bằng chứng quan sát

Hỏi: Sau hành động, điều gì chứng minh yêu cầu đã được đáp ứng?

Có thể là:

- Giá trị hoặc đối tượng trả về.
- Status code, header và nội dung phản hồi.
- Dữ liệu có thể truy vấn sau thao tác.
- Thông điệp hoặc sự kiện được phát ra.
- Một tác động bị ngăn chặn, chẳng hạn không tạo thanh toán khi đơn hàng không hợp lệ.
- Một lỗi cụ thể được trả về và trạng thái hệ thống vẫn được bảo toàn.

Chọn bằng chứng trực tiếp nhất. Nếu mục tiêu là API trả về 403, không cần kiểm tra private method trong bộ lọc bảo mật đã được gọi.

### Bước 6: Tách các kết quả khác nhau thành các mục tiêu riêng

Một yêu cầu thường có nhiều nhánh: hợp lệ, không hợp lệ, thiếu quyền, không tìm thấy dữ liệu, vượt giới hạn hoặc gặp lỗi dependency. Nếu mỗi nhánh có kết quả khác nhau, hãy viết các mục tiêu riêng.

Ví dụ với đăng nhập:

1. Tài khoản hợp lệ và mật khẩu đúng: đăng nhập thành công.
2. Mật khẩu sai: đăng nhập bị từ chối.
3. Tài khoản bị khóa: đăng nhập bị từ chối theo chính sách tài khoản.

Việc tách này giúp tên test mô tả rõ hành vi, dữ liệu chuẩn bị đơn giản và lỗi dễ được định vị.

## 4. Ví dụ: chọn hành vi cho một REST controller

Giả sử API có endpoint tạo đơn hàng. Tiêu chí chấp nhận quy định rằng dữ liệu hợp lệ tạo ra đơn hàng mới và client nhận được mã định danh của đơn hàng.

Mục tiêu kiểm thử:

> Khi client gửi POST /api/orders với dữ liệu hợp lệ, endpoint trả về HTTP 201, header Location trỏ đến đơn hàng mới và response body chứa mã đơn hàng cùng trạng thái PENDING.

Mục tiêu này hướng đến hợp đồng HTTP mà client sử dụng. Với Spring MVC, có thể dùng @WebMvcTest và MockMvc để kiểm tra controller ở ranh giới HTTP:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void returnsCreatedResponseWhenOrderRequestIsValid() throws Exception {
        given(orderService.create(any(CreateOrderRequest.class)))
                .willReturn(new OrderResponse("ord-42", "PENDING"));

        mockMvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "customerId": "cus-7",
                                  "productId": "prd-3",
                                  "quantity": 2
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(header().string(
                        HttpHeaders.LOCATION, "/api/orders/ord-42"))
                .andExpect(jsonPath("$.id").value("ord-42"))
                .andExpect(jsonPath("$.status").value("PENDING"));
    }
}
```

Trong ví dụ này:

- MockMvc gửi request qua hạ tầng Spring MVC mà không cần mở cổng HTTP thật.
- Service được thay bằng mock để bài test tập trung vào ánh xạ request, xử lý controller và định dạng response.
- Các assertion kiểm tra những phần client có thể quan sát: status, Location và JSON body.

Đây là bài kiểm thử hợp đồng của controller. Vì service đang được mock, bài test này **không chứng minh** dữ liệu đã được lưu vào cơ sở dữ liệu. Nếu yêu cầu còn bao gồm việc đơn hàng thực sự được lưu, cần một mục tiêu kiểm thử khác ở ranh giới service/repository hoặc một bài kiểm thử tích hợp bao phủ luồng tạo đơn hàng.

Lưu ý: @MockitoBean có trong Spring Framework 6.2 trở lên. Với dự án sử dụng phiên bản Spring Boot cũ hơn, hãy dùng cơ chế thay thế bean phù hợp với phiên bản của dự án, chẳng hạn @MockBean trong các phiên bản còn hỗ trợ.

### Tách hành vi lỗi thành mục tiêu riêng

Nếu số lượng đặt hàng phải lớn hơn 0, đây là một hành vi khác:

> Khi client gửi yêu cầu tạo đơn hàng với quantity bằng 0, API trả về HTTP 400 cùng thông tin lỗi hợp lệ và không tạo đơn hàng.

Bài test tương ứng nên kiểm tra phản hồi lỗi mà client nhận được. Nếu “không tạo đơn hàng” là một phần của cam kết, cần quan sát trạng thái dữ liệu hoặc dùng một ranh giới kiểm thử đủ để xác nhận không có đơn hàng mới. Chỉ kiểm tra status 400 chưa đủ để chứng minh không có tác động phụ.

## 5. Ví dụ: chọn hành vi cho repository

Repository có thể có hợp đồng riêng, chẳng hạn tìm khách hàng theo email không phân biệt chữ hoa chữ thường.

Mục tiêu:

> Khi cơ sở dữ liệu có khách hàng với email Lan@example.com, truy vấn bằng lan@EXAMPLE.com trả về khách hàng đó.

Với Spring Data JPA, @DataJpaTest phù hợp để kiểm tra hành vi repository cùng cấu hình persistence:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    @Test
    void findsCustomerByEmailIgnoringCase() {
        customerRepository.saveAndFlush(
                new Customer("Lan@example.com"));

        var result = customerRepository
                .findByEmailIgnoreCase("lan@EXAMPLE.com");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getEmail())
                .isEqualTo("Lan@example.com");
    }
}
```

Ở đây, bằng chứng là kết quả truy vấn thực tế. Kiểm tra rằng Spring Data tạo một proxy repository hoặc gọi một phương thức nội bộ cụ thể không xác nhận được hợp đồng truy vấn này.

@DataJpaTest thường cấu hình một database phù hợp cho kiểm thử và chạy test trong transaction được rollback sau mỗi test. Nếu ứng dụng phụ thuộc vào hành vi riêng của hệ quản trị cơ sở dữ liệu đang dùng trong production, hãy kiểm thử với cùng loại database, thường thông qua Testcontainers, để kết quả phản ánh đúng môi trường thực tế.

## 6. Chọn phạm vi kiểm thử trong Spring

Sau khi xác định hành vi, chọn loại test có thể quan sát hành vi đó với chi phí hợp lý.

| Hành vi cần kiểm tra | Phạm vi phù hợp | Lý do |
|---|---|---|
| Quy tắc tính toán hoặc quyết định thuần Java | Unit test cho class/service | Chạy nhanh, tập trung vào đầu vào và kết quả |
| HTTP status, header, JSON, validation hoặc mapping | @WebMvcTest với MockMvc | Kiểm tra hợp đồng MVC mà không cần khởi động toàn bộ ứng dụng |
| Truy vấn, mapping entity và ràng buộc persistence | @DataJpaTest | Tập trung vào JPA và database |
| Nhiều bean phối hợp qua cấu hình Spring | @SpringBootTest | Kiểm tra wiring và luồng tích hợp rộng hơn |
| Xử lý request qua server HTTP thực | @SpringBootTest kết hợp web environment phù hợp | Kiểm tra cả server và giao tiếp HTTP thực tế |
| Bảo mật endpoint | @WebMvcTest hoặc @SpringBootTest có cấu hình security | Quan sát quyền truy cập qua phản hồi thực tế |

Không nên mặc định dùng @SpringBootTest cho mọi hành vi. Nếu mục tiêu chỉ là kiểm tra một quy tắc tính giá, khởi động toàn bộ application context làm test chậm và khiến lỗi khó khoanh vùng. Ngược lại, nếu mục tiêu là xác nhận nhiều bean được cấu hình và phối hợp đúng, một unit test với mock có thể bỏ sót lỗi wiring.

Hãy chọn phạm vi dựa trên ranh giới đã xác định ở bước thiết kế, không dựa trên thói quen dùng một annotation cho mọi test.

## 7. Khi nào nên kiểm tra trạng thái và khi nào nên kiểm tra tương tác?

Kiểm tra trạng thái hoặc đầu ra thường là cách trực tiếp để chứng minh hành vi:

- Service trả về kết quả nghiệp vụ đúng.
- Repository đọc được dữ liệu sau khi lưu.
- API trả về status và body theo hợp đồng.
- Đơn hàng chuyển từ PENDING sang PAID sau khi thanh toán thành công.

Kiểm tra tương tác với dependency hữu ích khi giao tiếp đó là một phần của cam kết. Ví dụ, khi đơn hàng không hợp lệ, hệ thống không được gửi yêu cầu trừ tiền. Có thể dùng mock để xác nhận gateway thanh toán không nhận lệnh charge.

```java
verify(paymentGateway, never()).charge(any());
```

Assertion này có ý nghĩa vì việc gọi gateway có thể gây ra tác động bên ngoài. Ngược lại, xác nhận service gọi một helper nội bộ đúng hai lần thường không có ý nghĩa nghiệp vụ. Nếu lập trình viên đổi thuật toán nhưng vẫn giữ nguyên kết quả và cam kết tích hợp, test dựa trên số lần gọi helper sẽ thất bại dù hành vi vẫn đúng.

Một nguyên tắc hữu ích là: ưu tiên quan sát kết quả; kiểm tra tương tác khi ranh giới giao tiếp hoặc tác động bên ngoài là điều cần bảo đảm.

## 8. Những lỗi thường gặp khi chọn mục tiêu

### Chọn tên phương thức thay cho hành vi

Tên như testCreateOrder hoặc testUpdateUser chưa mô tả điều gì phải đúng. Một tên rõ hơn là returnsCreatedResponseWhenOrderIsValid hoặc rejectsLoginWhenAccountIsLocked. Tên test nên nói lên điều kiện và kết quả quan sát được.

### Mục tiêu quá rộng

“Kiểm tra chức năng quản lý đơn hàng” có thể bao gồm tạo, sửa, hủy, thanh toán và tìm kiếm. Khi có lỗi, mục tiêu rộng khiến khó xác định nhánh nào bị hỏng. Hãy chia theo từng hành vi có kết quả riêng.

### Chỉ kiểm tra rằng không có exception

Một thao tác chạy mà không ném exception chưa chắc đã làm đúng việc. Nếu mục tiêu là cập nhật trạng thái đơn hàng, hãy kiểm tra trạng thái mới. Nếu mục tiêu là API trả về đơn hàng, hãy kiểm tra response body.

### Chỉ xác nhận lời gọi mock

Test có thể xác nhận repository.save được gọi nhưng vẫn không chứng minh dữ liệu được lưu đúng hoặc API trả về đúng nội dung. Hãy xác định liệu tương tác đó có phải cam kết cần kiểm tra hay chỉ là cách triển khai hiện tại.

### Kiểm tra quá nhiều chi tiết nội bộ

Kiểm tra private method, thứ tự gọi helper hoặc tên bean cụ thể làm test phụ thuộc vào cấu trúc code. Khi cấu trúc thay đổi, test có thể hỏng dù hành vi không đổi. Chuyển assertion về public boundary hoặc kết quả mà thành phần sử dụng có thể quan sát.

### Không xác định điều kiện ban đầu

Một test tạo dữ liệu tùy tiện rồi gọi service có thể không thể hiện được tại sao kết quả mong đợi là đúng. Hãy ghi rõ trạng thái tài khoản, đơn hàng, kho hoặc quyền người dùng trước khi kích hoạt hành vi.

### Khẳng định vượt quá phạm vi test

Test controller với service mock không chứng minh database đã cập nhật. Test repository không chứng minh endpoint trả về đúng status code. Khi báo cáo kết quả, chỉ kết luận trong phạm vi hành vi và ranh giới mà test thực sự quan sát.

## 9. Xử lý hành vi bất đồng bộ và tác động bên ngoài

Một số hành vi không hoàn tất ngay trong lời gọi ban đầu. Ví dụ, controller phát sự kiện và listener cập nhật trạng thái đơn hàng sau đó. Khi chọn mục tiêu, hãy xác định chính xác kết quả cuối cùng cần quan sát và thời điểm kết quả được kỳ vọng xuất hiện.

Với xử lý bất đồng bộ:

- Xác định sự kiện hoặc thông điệp đầu vào.
- Xác định trạng thái, sự kiện hoặc tác động đầu ra cần có.
- Chờ theo điều kiện có giới hạn thời gian thay vì dùng Thread.sleep cố định.
- Làm rõ hành vi khi thông điệp được gửi lại, xử lý trùng hoặc dependency tạm thời lỗi nếu đó là yêu cầu của hệ thống.

Ví dụ, mục tiêu có thể là: “Khi listener nhận sự kiện OrderPaid hợp lệ, đơn hàng tương ứng cuối cùng chuyển sang PAID.” Test cần quan sát trạng thái cuối cùng hoặc sự kiện đầu ra. Việc listener gọi một phương thức helper không chứng minh được trạng thái đã chuyển.

Với dịch vụ bên ngoài như cổng thanh toán hoặc gửi email, không nhất thiết phải gọi dịch vụ thật trong mọi test. Có thể dùng mock hoặc fake ở ranh giới tích hợp để kiểm tra yêu cầu gửi đi và phản ứng của ứng dụng. Một bài kiểm thử tích hợp riêng có thể xác nhận cấu hình hoặc giao tiếp thật khi điều đó cần thiết.

## 10. Mẫu ghi mục tiêu trước khi viết test

Trước khi tạo test method, hãy ghi một câu mô tả hành vi theo mẫu:

```text
Khi [trạng thái ban đầu và điều kiện],
và [tác nhân thực hiện hành động],
hệ thống phải [kết quả quan sát được].

Ranh giới quan sát: [API / service / repository / event / integration].
Bằng chứng: [response / return value / persisted state / event / side effect].
```

Ví dụ hoàn chỉnh:

```text
Khi đơn hàng đang ở trạng thái PENDING và giao dịch thanh toán được xác nhận thành công,
listener xử lý sự kiện OrderPaid,
hệ thống phải chuyển đơn hàng sang trạng thái PAID.

Ranh giới quan sát: trạng thái đơn hàng qua repository.
Bằng chứng: truy vấn lại đơn hàng và nhận được trạng thái PAID.
```

Từ mô tả này, người viết test có thể chuẩn bị đơn hàng PENDING, kích hoạt listener bằng sự kiện phù hợp, rồi truy vấn trạng thái. Test không cần biết listener gọi những phương thức private nào.

## 11. Câu hỏi giúp làm rõ mục tiêu

Khi một yêu cầu còn mơ hồ, hãy dùng các câu hỏi sau để làm rõ trước khi viết test:

1. Thành phần hoặc người dùng nào đang sử dụng hành vi này?
2. Trạng thái ban đầu nào làm hành vi có ý nghĩa?
3. Hành động nào kích hoạt hệ thống?
4. Kết quả nào người quan sát có thể nhận biết?
5. Kết quả lỗi hoặc tác động bị ngăn chặn nào cũng thuộc yêu cầu?
6. Ranh giới kiểm thử nào cho phép quan sát kết quả trực tiếp nhất?
7. Có nhánh nào tạo ra một kết quả khác và cần mục tiêu riêng không?

Nếu chưa trả lời được “điều gì phải thay đổi hoặc được trả về sau hành động?”, mục tiêu vẫn chưa đủ rõ. Hãy quay lại yêu cầu, tiêu chí chấp nhận hoặc hợp đồng tích hợp để xác định kết quả mong đợi.

## Kết luận

Chọn một hành vi có thể quan sát làm mục tiêu nghĩa là xác định rõ điều kiện, hành động và kết quả mà một thành phần sử dụng có thể nhận biết. Trong ứng dụng Spring, mục tiêu đó quyết định ranh giới cần kiểm thử và loại test phù hợp: unit test, @WebMvcTest, @DataJpaTest hay @SpringBootTest. Khi mục tiêu được diễn đạt bằng kết quả cụ thể, test dễ đọc, dễ chẩn đoán và vẫn có giá trị khi cách triển khai bên trong được thay đổi.
