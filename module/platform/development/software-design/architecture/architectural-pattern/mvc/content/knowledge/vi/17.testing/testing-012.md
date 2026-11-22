# Giảm kiểm thử dễ vỡ do bám sát chi tiết triển khai

Kiểm thử giúp xác nhận ứng dụng MVC tiếp tục đáp ứng đúng yêu cầu khi mã nguồn thay đổi. Tuy nhiên, một bộ kiểm thử có thể trở thành trở ngại nếu nó phụ thuộc quá chặt vào cách lập trình viên tổ chức bên trong Controller, Service, Model hoặc View. Khi đổi tên phương thức private, tách một service thành hai lớp, thay thư viện mapping hoặc sắp xếp lại HTML mà hành vi người dùng không đổi, các kiểm thử như vậy vẫn thất bại.

Kiểm thử dễ vỡ (brittle test) thường đo cấu trúc hiện tại của mã nguồn thay vì hành vi mà hệ thống cần bảo đảm. Mục tiêu của bài này là thiết kế kiểm thử đủ nhạy để phát hiện lỗi có ý nghĩa, nhưng đủ ổn định để cho phép refactor an toàn. Trong MVC, điều đó có nghĩa là ưu tiên hợp đồng giữa request, nghiệp vụ và response; kiểm tra trạng thái, kết quả và tác dụng phụ quan trọng; chỉ kiểm tra tương tác nội bộ khi tương tác đó thực sự là một phần của yêu cầu.

## 1. Kiểm thử hành vi và kiểm thử chi tiết triển khai

Một hệ thống có thể được triển khai theo nhiều cách nhưng vẫn cung cấp cùng một hành vi bên ngoài. Ví dụ, trang chi tiết đơn hàng có thể được xây dựng bằng một query service, nhiều repository hoặc một truy vấn projection. Nếu người dùng vẫn nhận đúng đơn hàng, đúng tổng tiền và đúng quyền truy cập, thay đổi cấu trúc bên trong không nên buộc phải sửa hàng loạt kiểm thử.

| Kiểm thử tập trung vào | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Hành vi | Người dùng hoặc client quan sát được điều gì? | GET đơn hàng hợp lệ trả 200 và đúng dữ liệu |
| Hợp đồng | Hai thành phần phải tuân theo điều gì? | API trả mã trạng thái và trường JSON đã công bố |
| Quy tắc nghiệp vụ | Điều gì phải luôn đúng? | Không thể hủy đơn đã giao |
| Tương tác có ý nghĩa | Tác dụng phụ nào phải xảy ra hoặc không được xảy ra? | Thanh toán chỉ được gửi một lần |
| Chi tiết triển khai | Mã nguồn hiện được chia lớp hoặc gọi hàm ra sao? | Controller gọi mapper trước hay sau helper private |

Các loại kiểm thử đều có thể hữu ích, nhưng kiểm thử chi tiết triển khai không nên chiếm phần lớn. Một bài test chỉ chứng minh rằng phương thức A gọi B rồi gọi C thường không nói được liệu người dùng có nhận đúng kết quả hay không.

Một phép thử nhanh khi viết test là: **nếu thay đổi cách tổ chức bên trong nhưng giữ nguyên hành vi và hợp đồng, test có nên tiếp tục pass không?** Nếu câu trả lời là có mà test lại thất bại, có thể test đang gắn với chi tiết không cần thiết.

## 2. Một ví dụ về test dễ vỡ

Giả sử Controller hiển thị đơn hàng bằng cách gọi query service rồi chuyển kết quả thành ViewModel. Một test có thể kiểm tra chính xác chuỗi lời gọi:

~~~java
@Test
void detailCallsRepositoryThenMapperInExpectedOrder() {
    InOrder order = inOrder(repository, mapper);

    controller.detail(42L, currentUser, model);

    order.verify(repository).findForCustomer(42L, currentUser.id());
    order.verify(mapper).toDetail(any());
    verify(model).addAttribute(eq("order"), any());
}
~~~

Test này gắn với giả định rằng Controller trực tiếp gọi repository và mapper theo đúng thứ tự đó. Nếu sau này nhóm phát triển chuyển việc tải dữ liệu sang OrderQueryService, hoặc query service trả sẵn một projection, hành vi trang không đổi nhưng test thất bại.

Thay vào đó, kiểm tra response hoặc model ở ranh giới MVC:

~~~java
@Test
void detailShowsTheRequestedOrder() throws Exception {
    mockMvc.perform(get("/orders/42"))
            .andExpect(status().isOk())
            .andExpect(view().name("orders/detail"))
            .andExpect(model().attributeExists("order"))
            .andExpect(result -> {
                OrderDetailViewModel viewModel =
                        (OrderDetailViewModel) result.getModelAndView()
                                .getModel().get("order");
                assertThat(viewModel.orderNumber()).isEqualTo("ORD-42");
            });
}
~~~

Test này vẫn có thể chạy khi Controller thay đổi cách lấy hoặc ánh xạ dữ liệu, miễn là hợp đồng của trang còn nguyên. Trong test MVC thực tế, có thể dùng fixture hoặc matcher cho một số trường có ý nghĩa thay vì so sánh toàn bộ object nếu nhiều trường không liên quan.

## 3. Xác định hợp đồng trước khi viết test

Hợp đồng là những điều mà một thành phần cam kết với thành phần khác hoặc với người dùng. Trong MVC, hợp đồng thường xuất hiện ở nhiều ranh giới:

- HTTP method, URL, query parameter và path variable.
- Mã trạng thái, header và redirect URL.
- Cấu trúc JSON hoặc dữ liệu được đưa vào View.
- Quy tắc validation và cách lỗi được phản hồi.
- Quy tắc quyền truy cập.
- Thay đổi trạng thái nghiệp vụ và tác dụng phụ.

Ví dụ hợp đồng của endpoint tạo đơn:

1. Request POST hợp lệ tạo một đơn hàng.
2. Response chuyển hướng đến trang chi tiết hoặc trả JSON theo API contract.
3. Request thiếu dữ liệu bắt buộc không tạo đơn.
4. Người dùng không có quyền không thể xem hoặc sửa đơn của người khác.
5. Tổng tiền trong response phản ánh quy tắc nghiệp vụ đã áp dụng.

Khi hợp đồng được viết rõ, test có thể xác nhận các điều đó mà không cần biết Controller dùng bao nhiêu helper hoặc service có bao nhiêu lớp.

## 4. Kiểm thử Controller qua ranh giới HTTP

Controller là adapter giữa HTTP và use case. Kiểm thử Controller nên tập trung vào việc ánh xạ request, gọi use case đúng dữ liệu và tạo response đúng hợp đồng.

### 4.1. Kiểm tra kết quả HTTP

Với Spring MVC, MockMvc cho phép gửi request và kiểm tra status, header, body, View và model mà không cần khởi chạy server thật.

~~~java
@WebMvcTest(OrderApiController.class)
class OrderApiControllerTest {
    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderQueryService orders;

    @Test
    void returnsOrderDetailsAsJson() throws Exception {
        given(orders.getDetails(42L, 7L))
                .willReturn(orderDetailsResult(42L));

        mockMvc.perform(get("/api/orders/42")
                .with(authentication(authenticationFor(7L))))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                ))
                .andExpect(jsonPath("$.orderNumber").value("ORD-42"))
                .andExpect(jsonPath("$.status").value("PLACED"));
    }
}
~~~

Đây là ví dụ minh họa; cấu hình test cần cung cấp CurrentUser hoặc cơ chế principal tương ứng với ứng dụng. Annotation MockitoBean có trong các phiên bản Spring Framework mới; ở dự án dùng phiên bản cũ hơn, dùng cơ chế mock bean được phiên bản đó hỗ trợ.

Hàm authenticationFor là fixture của test, tạo Authentication có principal đúng kiểu CurrentUser mà Controller yêu cầu. Các import và phần cấu hình bảo mật chung được lược bỏ để tập trung vào assertion.

Test xác nhận client nhận được JSON với các trường có ý nghĩa. Nó không yêu cầu Controller phải dùng mapper cụ thể, không kiểm tra tên biến cục bộ và không kiểm tra thứ tự các lời gọi private.

### 4.2. Kiểm tra validation qua response

Với request sai, điều quan trọng là server trả lỗi theo hợp đồng và không thực hiện thay đổi nghiệp vụ:

~~~java
@Test
void rejectsInvalidCreateRequest() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "productId": 42,
                              "quantity": 0
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"));

    verifyNoInteractions(orderCommandService);
}
~~~

Trong test class này, orderCommandService là bean mock được đăng ký bằng @MockitoBean hoặc cơ chế tương đương của phiên bản Spring đang dùng.

Ở đây, xác nhận service không được gọi là một kiểm tra tương tác có ý nghĩa: request không hợp lệ không được tạo đơn. Nó bảo vệ một ranh giới nghiệp vụ, không phải một thứ tự gọi nội bộ tùy ý.

Không nên kiểm tra toàn bộ thông điệp lỗi nếu thông điệp có thể được dịch hoặc diễn đạt lại mà hợp đồng không yêu cầu câu chữ cố định. Hãy ưu tiên mã lỗi, trường lỗi và status ổn định; chỉ kiểm tra nội dung nguyên văn khi đó là một phần được công bố của sản phẩm.

### 4.3. Kiểm tra redirect và Post/Redirect/Get

Nếu ứng dụng dùng PRG, test nên xác nhận response chuyển hướng đến URL kết quả:

~~~java
@Test
void redirectsAfterSuccessfulOrderCreation() throws Exception {
    given(orderCommandService.create(any()))
            .willReturn(new CreatedOrder(42L));

    mockMvc.perform(post("/orders")
                    .with(csrf())
                    .param("productId", "9")
                    .param("quantity", "2"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/orders/42"));
}
~~~

Nếu mã trạng thái 303 là một yêu cầu cụ thể, hãy kiểm tra chính xác status 303. Nếu hợp đồng chỉ yêu cầu chuyển hướng mà không quy định mã, kiểm tra is3xxRedirection() có thể ổn định hơn. Mức độ chính xác của assertion nên tương ứng với mức độ chính xác của hợp đồng.

## 5. Không kiểm thử phương thức private trực tiếp

Phương thức private là chi tiết triển khai của lớp. Nếu một phương thức private khó kiểm thử, thường có hai khả năng:

- Hành vi đó nên được kiểm tra thông qua public API của lớp.
- Logic đã đủ lớn để trở thành một thành phần có trách nhiệm riêng và có thể kiểm thử độc lập.

Ví dụ không nên dùng reflection để gọi calculateDiscount() private. Hãy kiểm tra kết quả của use case áp dụng giảm giá:

~~~java
@Test
void appliesEligibleDiscountToOrderTotal() {
    Order order = orderWithSubtotal("100.00");

    order.applyDiscount(Discount.percent(10));

    assertThat(order.total().amount())
            .isEqualByComparingTo("90.00");
}
~~~

Test kiểm tra quy tắc miền qua API công khai của Order. Lớp có thể đổi tên hoặc chia nhỏ các helper nội bộ mà test không cần thay đổi.

Nếu logic tính giảm giá được dùng ở nhiều nơi và có nhiều quy tắc độc lập, có thể tách thành DiscountPolicy với API công khai. Khi đó, test trực tiếp policy là hợp lý vì policy đã trở thành một đơn vị thiết kế có trách nhiệm rõ ràng.

## 6. Dùng mock đúng ranh giới

Mock hữu ích để cô lập một thành phần khỏi hệ thống bên ngoài hoặc cộng tác viên đắt đỏ, không ổn định. Tuy nhiên, mock quá nhiều lớp nội bộ khiến test phải biết cấu trúc triển khai.

### 6.1. Mock collaborator ở ranh giới

Trong unit test của application service, có thể mock repository hoặc cổng thanh toán để kiểm tra kết quả use case. Ví dụ:

~~~java
@Test
void placesOrderWhenStockIsAvailable() {
    given(inventory.reserve(9L, 2)).willReturn(Reservation.accepted());
    given(orders.save(any(Order.class)))
            .willAnswer(invocation -> invocation.getArgument(0));

    PlaceOrderResult result = service.place(
            new PlaceOrderCommand(9L, 2, 7L)
    );

    assertThat(result.status()).isEqualTo(OrderStatus.PLACED);
    assertThat(result.quantity()).isEqualTo(2);
    verify(inventory).reserve(9L, 2);
}
~~~

Ở đây inventory là collaborator có tác dụng phụ và ranh giới với một tài nguyên khác. Việc xác nhận yêu cầu giữ chỗ đã được gửi có ý nghĩa với use case.

### 6.2. Tránh mock mọi lớp trong cùng một luồng

Một test tạo mock cho Controller, Mapper, Assembler, Service, Policy và Repository rồi xác nhận từng lời gọi có thể thất bại sau một refactor thuần túy. Nếu một lớp được tách hoặc gộp nhưng hợp đồng bên ngoài không đổi, các test như vậy tạo chi phí bảo trì mà không tăng nhiều độ tin cậy.

Hãy chọn một ranh giới để kiểm tra:

- Unit test domain object hoặc policy với dữ liệu thật.
- Unit test application service với mock các cổng bên ngoài.
- MVC slice test cho HTTP mapping và response.
- Integration test cho repository, transaction và cache provider.

Không cần mock mọi dependency trong mọi loại test. Càng nhiều mock được thiết lập theo cấu trúc nội bộ, test càng dễ trở thành bản sao của implementation.

### 6.3. Khi nào nên verify interaction?

Verify interaction phù hợp khi lời gọi hoặc việc không gọi một collaborator là một phần của hành vi:

- Không gửi lệnh thanh toán nếu dữ liệu đầu vào không hợp lệ.
- Không gửi email xác nhận khi transaction tạo đơn thất bại.
- Chỉ gửi một lệnh giữ chỗ cho một lần đặt hàng.
- Không gọi dịch vụ bên ngoài khi người dùng không được phép.

Tránh verify:

- Một getter đã được gọi bao nhiêu lần.
- Mapper nội bộ được gọi trước helper nào.
- Repository được gọi bằng một phương thức cụ thể khi nhiều truy vấn có thể đáp ứng cùng hợp đồng.
- Một logger ghi đúng chuỗi debug nội bộ.

Không có quy tắc “không bao giờ dùng verify”. Câu hỏi là tương tác đó có quan trọng với hành vi hoặc tác dụng phụ mà test đang bảo vệ hay không.

## 7. Kiểm thử Model và quy tắc nghiệp vụ độc lập với MVC

Model nên được kiểm tra qua trạng thái và hành vi công khai. Những test này thường rất ổn định vì chúng gắn với quy tắc nghiệp vụ thay vì framework.

~~~java
@Test
void shippedOrderCannotBeCancelled() {
    Order order = orderWithStatus(OrderStatus.SHIPPED);

    assertThatThrownBy(order::cancel)
            .isInstanceOf(OrderCannotBeCancelledException.class);

    assertThat(order.status()).isEqualTo(OrderStatus.SHIPPED);
}
~~~

Test không cần biết Order dùng enum hay state object, lưu lịch sử trạng thái trong list hay event collection. Nó chỉ xác nhận bất biến: đơn đã giao không thể bị hủy.

Đối với state machine, hãy kiểm tra các chuyển trạng thái được phép và bị cấm:

| Trạng thái hiện tại | Lệnh | Kết quả mong đợi |
|---|---|---|
| PLACED | Pay | PAID |
| PAID | Ship | SHIPPED |
| PLACED | Cancel | CANCELLED |
| SHIPPED | Cancel | Bị từ chối |
| CANCELLED | Ship | Bị từ chối |

Có thể dùng parameterized test cho bảng chuyển trạng thái. Test theo bảng nghiệp vụ thường dễ đọc và bền hơn test từng nhánh private.

## 8. Kiểm thử View mà không khóa vào cấu trúc HTML

View có thể được chỉnh sửa thường xuyên để cải thiện bố cục, khả năng truy cập hoặc responsive design. Nếu test tìm phần tử bằng chuỗi CSS sâu như div.container > div:nth-child(2) > span.status, thay đổi bố cục vô hại cũng khiến test hỏng.

Ưu tiên xác nhận nội dung và khả năng tương tác có ý nghĩa:

- Người dùng nhìn thấy tiêu đề đơn hàng và trạng thái.
- Trường biểu mẫu có label và validation message phù hợp.
- Nút thao tác xuất hiện khi người dùng có quyền.
- Liên kết điều hướng đến tài nguyên đúng.
- Nội dung quan trọng có thể truy cập bằng tên/role ngữ nghĩa.

Với browser test, dùng locator theo role, accessible name, label hoặc test ID ổn định được thiết kế có chủ đích. Hạn chế selector phụ thuộc vào thứ bậc DOM, class CSS dùng cho trang trí hoặc vị trí phần tử.

Ví dụ ý tưởng với Playwright:

~~~typescript
await page.getByRole("heading", { name: "Đơn hàng ORD-42" }).waitFor();
await expect(
  page.getByText("Đã thanh toán", { exact: true })
).toBeVisible();
await expect(
  page.getByRole("button", { name: "Yêu cầu hủy" })
).toHaveCount(0);
~~~

Test này tập trung vào điều người dùng có thể nhận biết. Nếu nhóm thay đổi từ div sang section hoặc chuyển trạng thái vào một component khác, test vẫn có thể pass.

### 8.1. Tránh snapshot toàn bộ trang một cách máy móc

Snapshot có thể hữu ích để phát hiện thay đổi giao diện có chủ đích, nhưng snapshot quá lớn thường thay đổi vì khoảng trắng, thứ tự thuộc tính, nội dung thời gian hoặc dữ liệu ngẫu nhiên. Khi snapshot hỏng, người đọc khó biết thay đổi nào là quan trọng.

Nếu dùng snapshot:

- Giữ phạm vi nhỏ, tập trung vào một component hoặc vùng nội dung.
- Dùng dữ liệu fixture ổn định.
- Loại bỏ giá trị động không thuộc hành vi cần kiểm tra.
- Review diff trước khi cập nhật snapshot.
- Kết hợp assertion ngữ nghĩa cho hành vi quan trọng.

Snapshot là công cụ so sánh, không phải bằng chứng tự động rằng giao diện đúng.

## 9. Chọn đúng loại test cho đúng ranh giới

Không phải mọi yêu cầu đều cần end-to-end test. Một chiến lược MVC cân bằng thường có nhiều lớp:

| Loại test | Phạm vi | Điều nên xác nhận |
|---|---|---|
| Unit test Model | Entity, value object, policy | Bất biến, tính toán, chuyển trạng thái |
| Unit test application service | Một use case | Điều phối nghiệp vụ và kết quả |
| MVC slice test | Controller, binding, serialization, View | HTTP contract, validation, quyền, redirect |
| Repository integration test | ORM và database | Truy vấn, mapping, transaction, constraint |
| Component/integration test | Nhiều bean thật trong một luồng | Cộng tác giữa các tầng và cấu hình |
| Browser end-to-end test | Trình duyệt đến server | Luồng người dùng quan trọng từ đầu đến cuối |

Đặt phần lớn ví dụ kiểm tra quy tắc nghiệp vụ ở unit test vì chúng nhanh và ít phụ thuộc framework. Dùng integration test cho những điều chỉ database hoặc framework thật mới chứng minh được. Giữ end-to-end test cho các hành trình quan trọng vì chúng thường chậm và nhạy với môi trường hơn.

Không nên cố kiểm tra cùng một chi tiết ở mọi lớp. Ví dụ, quy tắc “không thể hủy đơn đã giao” cần test sâu ở Model/use case; Controller test chỉ cần xác nhận lỗi đó được ánh xạ thành response phù hợp.

## 10. Fixture và dữ liệu kiểm thử ổn định

Dữ liệu kiểm thử khó hiểu làm test dễ vỡ và khó sửa. Tránh tạo object bằng một chuỗi constructor dài với nhiều giá trị không có ý nghĩa:

~~~java
Order order = new Order(42L, 7L, "A", 3, 125000, "VND",
        Instant.parse("2026-01-01T00:00:00Z"), false, null);
~~~

Thay vào đó, dùng factory hoặc test data builder:

~~~java
Order order = anOrder()
        .withId(42L)
        .forCustomer(7L)
        .withStatus(OrderStatus.PLACED)
        .withLine("Keyboard", 2, money("125000", "VND"))
        .build();
~~~

Builder nên có giá trị mặc định hợp lệ và chỉ nêu những thuộc tính liên quan đến test. Không tạo một framework fixture quá tổng quát khiến người đọc phải học thêm DSL phức tạp.

Dùng thời gian cố định thay cho đồng hồ thật:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-11-19T08:00:00Z"),
        ZoneOffset.UTC
);
~~~

Tránh phụ thuộc múi giờ máy chạy test, thứ tự dữ liệu database, ID tăng tự động cụ thể hoặc random không seed. Nếu một thuộc tính không quan trọng với hành vi đang test, đừng assert nó.

## 11. Tránh assertion quá rộng hoặc quá chính xác

Assertion cần đủ cụ thể để bắt lỗi, nhưng không nên ràng buộc những khác biệt không thuộc hợp đồng.

Ví dụ:

- Kiểm tra response có mã đơn và tổng tiền đúng thay vì so sánh toàn bộ JSON nếu thứ tự field không quan trọng.
- Kiểm tra status 303 nếu PRG yêu cầu 303; nếu chỉ yêu cầu redirect, dùng assertion 3xx.
- Kiểm tra mã lỗi ổn định thay vì toàn bộ câu thông báo có thể được dịch.
- Kiểm tra tập kết quả nếu thứ tự không được quy định; nếu thứ tự là yêu cầu, kiểm tra thứ tự rõ ràng.
- Kiểm tra tiền bằng so sánh số thập phân theo quy tắc scale thay vì so sánh chuỗi hiển thị theo locale.

Test không nên quá lỏng. Chỉ kiểm tra status 200 mà không xác nhận nội dung quan trọng có thể để lỗi dữ liệu lọt qua. Hãy xác định chính xác những thuộc tính có ý nghĩa đối với client hoặc quy tắc.

## 12. Kiểm thử phân quyền ở hành vi quan sát được

Quyền truy cập là hợp đồng bảo mật, vì vậy test cần xác nhận cả trường hợp được phép và bị từ chối. Không chỉ kiểm tra policy được gọi.

Ví dụ:

~~~java
@Test
void customerCannotReadAnotherCustomersOrder() throws Exception {
    mockMvc.perform(get("/api/orders/42")
                    .with(user("customer-7").roles("CUSTOMER")))
            .andExpect(status().isNotFound());
}
~~~

Test giả định chính sách của ứng dụng cố ý trả 404 để không tiết lộ tài nguyên tồn tại. Nếu hợp đồng chọn 403, hãy kiểm tra 403. Điều quan trọng là test xác nhận chính sách công khai đã chọn.

Ngoài ra, cần test:

- Người dùng đúng tenant và có quyền được truy cập.
- Người dùng cùng tenant nhưng không có quyền trên tài nguyên bị từ chối.
- Người dùng tenant khác không đọc hoặc cập nhật được dữ liệu.
- Quyền bị thu hồi có hiệu lực theo yêu cầu.
- Trường nhạy cảm không xuất hiện trong JSON hoặc ViewModel.

Tránh kiểm tra chi tiết cách framework lưu SecurityContext; hãy kiểm tra response và tác dụng phụ của request.

## 13. Kiểm thử cache, transaction và tích hợp

Một số hành vi chỉ có thể được xác nhận đáng tin cậy khi dùng thành phần thật:

- Cache key tách dữ liệu giữa hai tenant.
- Cache invalidation sau transaction commit.
- Rollback không để cache phản ánh dữ liệu chưa commit.
- Optimistic lock ngăn ghi đè cập nhật.
- Unique constraint chặn dữ liệu trùng.
- Repository projection trả đúng dữ liệu và không phát sinh N+1 ngoài dự kiến.

Không nên mock CacheManager trong test duy nhất rồi kết luận TTL và serialization hoạt động đúng. Có thể dùng provider phù hợp trong integration test, chẳng hạn cache in-memory cho hành vi cơ bản và provider tương tự production cho tính năng phụ thuộc Redis.

Test tích hợp nên cô lập dữ liệu bằng database riêng, schema riêng hoặc transaction/cleanup rõ ràng. Tránh dựa vào trạng thái do test khác tạo ra.

## 14. Refactor và test: ví dụ trước/sau

Giả sử ban đầu Controller tự tính tổng tiền và tự tạo response. Sau refactor, nhóm chuyển phép tính vào Order và mapping sang một mapper riêng.

~~~mermaid
flowchart LR
    subgraph Before[Trước refactor]
        C1[Controller] --> R1[Repository]
        C1 --> F1[Tính tổng và tạo View]
    end
    subgraph After[Sau refactor]
        C2[Controller] --> S2[Query Service]
        S2 --> M2[Domain Model]
        C2 --> P2[Presentation Mapper]
        P2 --> V2[ViewModel]
    end
~~~

Nếu test chỉ kiểm tra kết quả cuối cùng, chúng vẫn có thể pass sau refactor. Nếu test xác nhận Controller gọi repository rồi cộng từng dòng, test phải viết lại dù hành vi không đổi.

Refactor tốt thường làm cấu trúc dễ hiểu hơn mà không thay đổi hợp đồng. Bộ kiểm thử nên cho phép điều đó. Khi test thất bại sau refactor, hãy hỏi:

1. Hành vi hoặc hợp đồng có thực sự thay đổi không?
2. Nếu có, test có cần cập nhật theo yêu cầu mới không?
3. Nếu không, test có đang phụ thuộc vào một chi tiết triển khai không cần thiết?
4. Có thể chuyển assertion lên ranh giới công khai hoặc xuống đơn vị có trách nhiệm rõ hơn không?

Không cập nhật test một cách máy móc chỉ để làm CI xanh. Đọc failure và xác định nó báo lỗi hành vi hay chỉ báo cấu trúc đã đổi.

## 15. Dấu hiệu nhận biết bộ test đang dễ vỡ

| Dấu hiệu | Vì sao đáng ngờ | Hướng cải thiện |
|---|---|---|
| Dùng reflection gọi private method | Phụ thuộc cấu trúc lớp | Test qua API công khai hoặc tách policy |
| Verify nhiều lời gọi nội bộ | Test mô phỏng implementation | Assert kết quả và tác dụng phụ quan trọng |
| Mock mọi collaborator | Không còn kiểm tra được tích hợp thực | Chọn ranh giới test và dùng thành phần thật phù hợp |
| Snapshot toàn bộ HTML | Bị ảnh hưởng bởi thay đổi bố cục nhỏ | Assert nội dung và tương tác ngữ nghĩa |
| Selector CSS phụ thuộc DOM sâu | Refactor markup làm test hỏng | Dùng role, label, accessible name hoặc test ID |
| So sánh toàn bộ object lớn | Trường không liên quan gây failure | Assert các trường thuộc yêu cầu |
| Dùng thời gian/random thật | Kết quả không lặp lại | Clock cố định và fixture deterministic |
| Dựa vào thứ tự chạy test | Test không độc lập | Cô lập dữ liệu và cleanup |
| Assert câu lỗi nội bộ | Câu chữ thay đổi không có ý nghĩa | Dùng error code và field path ổn định |
| Test framework thay vì ứng dụng | Khóa vào chi tiết thư viện | Kiểm tra hợp đồng của ứng dụng |

## 16. Quy trình viết một test bền vững

Khi nhận một yêu cầu mới, có thể thực hiện theo các bước:

1. **Mô tả hành vi:** viết điều kiện đầu vào và kết quả quan sát được bằng ngôn ngữ người dùng hoặc nghiệp vụ.
2. **Chọn ranh giới:** xác định đây là quy tắc Model, use case, HTTP contract, persistence hay luồng trình duyệt.
3. **Chuẩn bị fixture:** tạo dữ liệu tối thiểu, hợp lệ và dễ hiểu.
4. **Thực hiện hành động:** gọi API công khai hoặc gửi request qua ranh giới cần kiểm tra.
5. **Assert kết quả:** kiểm tra trạng thái, dữ liệu, lỗi hoặc tác dụng phụ có ý nghĩa.
6. **Loại bỏ coupling thừa:** xem test có phụ thuộc private method, thứ tự gọi nội bộ, tên biến hoặc cấu trúc DOM không cần thiết không.
7. **Thử tư duy refactor:** hình dung thay implementation nhưng giữ hợp đồng; test có nên tiếp tục pass không?

Ví dụ yêu cầu “người dùng không thể đặt hàng khi tồn kho không đủ” nên có:

- Unit test cho quy tắc giữ chỗ hoặc domain policy.
- Application service test xác nhận không tạo đơn khi giữ chỗ thất bại.
- MVC test xác nhận client nhận lỗi phù hợp.
- Integration test khi cần xác nhận cập nhật tồn kho đồng thời trong database.

Không cần một browser test cho mọi biến thể số lượng nếu các tầng thấp hơn đã kiểm tra đầy đủ. Chỉ cần end-to-end test cho một hành trình đại diện có giá trị cao.

## 17. Checklist review một bài test MVC

Trước khi đưa test vào bộ kiểm thử, hãy tự hỏi:

- Test đang bảo vệ yêu cầu hoặc hợp đồng nào?
- Nó quan sát hành vi từ ranh giới phù hợp chưa?
- Assertion có đủ cụ thể để bắt lỗi thực tế không?
- Test có phụ thuộc tên phương thức private, field hoặc thứ tự gọi nội bộ không?
- Các mock có đại diện cho ranh giới bên ngoài hoặc tác dụng phụ quan trọng không?
- Dữ liệu fixture có rõ nghĩa và ổn định không?
- Test có phụ thuộc thời gian, locale, timezone, random hoặc trạng thái test khác không?
- Nếu thay đổi cấu trúc bên trong nhưng giữ hành vi, test có tiếp tục pass không?
- Nếu test thất bại, thông báo có chỉ rõ hành vi nào bị vi phạm không?
- Có thể kiểm tra ở lớp thấp hơn nhanh hơn mà vẫn giữ được độ tin cậy không?

## 18. Kết luận

Một bộ kiểm thử tốt không cố đóng băng cấu trúc hiện tại của ứng dụng. Nó bảo vệ những điều người dùng, client và các tầng nghiệp vụ có quyền kỳ vọng. Trong MVC, hãy kiểm tra Model qua bất biến và hành vi, application service qua kết quả use case, Controller qua hợp đồng HTTP, View qua nội dung và tương tác có ý nghĩa, còn persistence và cache qua integration test phù hợp.

Mock và verify vẫn có chỗ đứng khi chúng bảo vệ một tác dụng phụ hoặc ranh giới quan trọng. Nhưng nếu test biết quá nhiều về các lời gọi nội bộ, phương thức private hoặc cấu trúc DOM, mỗi lần refactor sẽ tạo ra nhiều công việc sửa test mà không tăng chất lượng sản phẩm. Hãy viết test để phát hiện thay đổi hành vi ngoài ý muốn và cho phép thay đổi cách triển khai một cách tự tin.
