# Đặt ngân sách thời gian và tiêu chí độc lập cho từng nhóm kiểm thử

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Giải thích vì sao mỗi nhóm kiểm thử cần có ngân sách thời gian và tiêu chí độc lập rõ ràng.
- Phân biệt thời gian thực thi của test với thời gian chuẩn bị môi trường, dữ liệu, chạy song song và thu thập kết quả.
- Xác định ngân sách phù hợp cho unit test, component test, contract test, integration test và các nhóm kiểm thử rộng hơn.
- Thiết kế kiểm thử có thể chạy riêng lẻ, lặp lại, chạy theo thứ tự bất kỳ và chạy song song mà không gây ảnh hưởng lẫn nhau.
- Nhận diện nguyên nhân làm kiểm thử chậm, phụ thuộc thứ tự hoặc không ổn định.
- Tổ chức pipeline theo các vòng phản hồi và theo dõi việc sử dụng ngân sách theo dữ liệu thực tế.

## 1. Vì sao cần ngân sách thời gian và tính độc lập?

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, unit test và integration test cần cung cấp phản hồi đáng tin cậy trong khoảng thời gian phù hợp với nhịp phát triển. Nếu bộ kiểm thử mất quá lâu, nhóm có xu hướng trì hoãn chạy, bỏ qua bước kiểm tra hoặc chỉ chạy một phần trước khi hợp nhất thay đổi. Nếu test phụ thuộc vào thứ tự, dữ liệu dùng chung hoặc trạng thái môi trường, kết quả có thể thay đổi giữa các lần chạy và khó xác định lỗi thực sự nằm ở đâu.

Hai yếu tố cần được thiết kế song song:

1. **Ngân sách thời gian (time budget)** xác định thời gian tối đa hoặc mục tiêu thời gian cho một nhóm kiểm thử, một lần chạy hoặc một giai đoạn trong pipeline. Ngân sách giúp nhóm biết phản hồi cần đến khi nào, nơi nào đang gây chậm và khi nào cần tối ưu.
2. **Tính độc lập (test independence)** bảo đảm kết quả của một test không phụ thuộc vào test khác, thứ tự thực thi, trạng thái còn sót lại hoặc dữ liệu do một tiến trình khác tạo ra. Tính độc lập giúp test có thể chạy riêng, lặp lại và song song một cách đáng tin cậy.

Một bộ unit test có thể chạy rất nhanh nhưng vẫn không đáng tin nếu test sau chỉ Pass khi test trước đã khởi tạo dữ liệu tĩnh. Một bộ integration test có thể kiểm tra đúng luồng nghiệp vụ nhưng không phù hợp làm cổng phản hồi nhanh nếu mỗi test phải khởi động toàn bộ hạ tầng, tải dữ liệu lớn và chờ dịch vụ bên ngoài. Ngược lại, tối ưu thời gian bằng cách bỏ qua kiểm tra hoặc dùng chung trạng thái có thể làm giảm giá trị bằng chứng.

Mục tiêu là chọn ngân sách thực tế cho từng nhóm và bảo đảm từng test có thể được thực thi trong điều kiện được kiểm soát.

## 2. Ngân sách thời gian là gì?

Ngân sách thời gian là giới hạn hoặc mục tiêu về thời gian dành cho hoạt động kiểm thử. Nó có thể áp dụng ở nhiều cấp:

- **Một test case**: thời gian tối đa để thực thi một trường hợp kiểm thử.
- **Một nhóm test**: tổng thời gian của unit, component, contract hoặc integration test trong một lần chạy.
- **Một giai đoạn pipeline**: thời gian từ khi bắt đầu đến khi nhóm nhận được kết quả và báo cáo.
- **Toàn bộ vòng phản hồi**: thời gian từ khi gửi thay đổi đến khi có tín hiệu đủ tin cậy để tiếp tục công việc.
- **Một hoạt động kiểm thử chuyên biệt**: thời gian dành cho migration, kiểm thử tải, kiểm thử phục hồi hoặc kiểm thử trên môi trường tích hợp.

Ngân sách có thể là mục tiêu vận hành hoặc ngưỡng bắt buộc. Ví dụ, nhóm có thể đặt mục tiêu unit test hoàn tất trong vài phút để hỗ trợ phản hồi thường xuyên, trong khi integration test có thể được phép lâu hơn vì cần khởi tạo database hoặc broker. Các con số cụ thể phải được xác định từ quy mô dự án, hạ tầng CI, mức độ song song và yêu cầu của tổ chức; không có một giới hạn đúng cho mọi hệ thống.

### 2.1. Phân biệt các thành phần thời gian

Khi đo thời gian, cần thống nhất điểm bắt đầu và kết thúc. Một lần chạy có thể bao gồm:

1. **Setup**: tạo môi trường, container, schema, dữ liệu và cấu hình.
2. **Execution**: thực thi các bước kiểm thử và chờ kết quả.
3. **Teardown**: dọn dữ liệu, đóng kết nối, dừng container hoặc giải phóng tài nguyên.
4. **Reporting**: tổng hợp kết quả, lưu log, trace, coverage và tạo báo cáo.
5. **Queueing / scheduling**: thời gian chờ runner hoặc tài nguyên CI sẵn sàng.

Thời gian thực thi test và thời gian từ lúc commit đến khi có kết quả là hai chỉ số khác nhau. Nếu một suite chạy trong 4 phút nhưng phải đợi runner 8 phút, người phát triển nhận phản hồi sau 12 phút. Tối ưu phần test mà không đo thời gian chờ có thể không cải thiện trải nghiệm thực tế.

Nên ghi nhận tối thiểu thời gian tổng, thời gian setup, thời gian thực thi và thời gian teardown. Với pipeline quan trọng, cần theo dõi thêm thời gian chờ tài nguyên và thời gian tạo báo cáo.

## 3. Đặt ngân sách theo mục tiêu của từng nhóm kiểm thử

Mỗi nhóm có phạm vi và chi phí khác nhau. Ngân sách nên phản ánh vai trò của nhóm trong vòng phản hồi.

| Nhóm kiểm thử | Mục tiêu chính | Đặc điểm thời gian thường gặp | Cách đặt ngân sách |
|---|---|---|---|
| Unit | Kiểm tra logic nhỏ và quy tắc độc lập | Rất nhiều test, mỗi test thường ngắn, ít phụ thuộc ngoài | Đặt mục tiêu tổng suite và giới hạn cho test bất thường chậm; ưu tiên phản hồi sớm. |
| Component | Kiểm tra một thành phần qua nhiều lớp nội bộ | Có thể cần cấu hình, database hoặc test double | Tách thời gian khởi tạo thành phần và thời gian test; đặt ngân sách theo component. |
| Contract | Kiểm tra tương thích giữa consumer và provider | Thường nhẹ hơn tích hợp toàn hệ thống nhưng có thể cần provider verification | Chạy sớm khi hợp đồng thay đổi; giới hạn thời gian tải hợp đồng và kiểm tra provider. |
| Integration | Kiểm tra tương tác giữa các thành phần thật | Tốn thời gian setup môi trường, dữ liệu và chờ I/O | Chia suite theo ranh giới; đặt ngân sách riêng cho setup, execution và cleanup. |
| System / end-to-end | Kiểm tra hành trình hoàn chỉnh | Thường chậm và nhạy với môi trường | Chọn tập đại diện, chạy ở giai đoạn phù hợp và có ngân sách riêng. |
| Performance / resilience | Đo tải, độ ổn định và phục hồi | Cần thời gian warm-up, giữ tải và quan sát | Xác định thời lượng đo, thời gian ổn định và điều kiện dừng trước khi chạy. |

Không nên dùng thời gian của một nhóm để che khuất vấn đề ở nhóm khác. Ví dụ, unit suite đạt mục tiêu nhưng component suite liên tục vượt ngân sách cần được phân tích riêng. Báo cáo nên thể hiện nhóm nào vượt ngưỡng và nguyên nhân chính.

### 3.1. Ngân sách cho unit test

Unit test thường nằm trong vòng phản hồi nhanh của lập trình viên và pipeline. Ngân sách nên khuyến khích:

- Test chỉ kiểm tra một hành vi hoặc một quy tắc chính.
- Không truy cập mạng, không gọi dịch vụ bên ngoài và không dùng database thật trừ khi phạm vi test được định nghĩa khác.
- Dữ liệu đầu vào nhỏ, được tạo trực tiếp hoặc qua fixture nhẹ.
- Không dùng sleep để chờ một trạng thái có thể xác định đồng bộ.
- Không phụ thuộc thứ tự chạy hoặc tài nguyên toàn cục có thể thay đổi.
- Khi test chậm, có thể xác định được đoạn setup, logic hoặc teardown gây chậm.

Một unit test chạy lâu bất thường có thể đang làm nhiều việc hơn phạm vi đơn vị: gọi file system, khởi tạo framework nặng, chờ thread, truy cập mạng hoặc dùng dữ liệu lớn. Hãy kiểm tra nguyên nhân trước khi chỉ tăng timeout.

### 3.2. Ngân sách cho integration test

Integration test thường cần tài nguyên thật hơn, chẳng hạn database, message broker, cache, HTTP server hoặc nhiều service. Ngân sách nên tách biệt:

- Thời gian cấp phát và khởi động phụ thuộc.
- Thời gian migration hoặc nạp dữ liệu chuẩn bị.
- Thời gian thực thi các kịch bản.
- Thời gian chờ sự kiện bất đồng bộ hoặc xử lý nền.
- Thời gian dọn dữ liệu và giải phóng môi trường.

Nếu setup chiếm phần lớn thời gian, có thể dùng container dùng chung trong phạm vi một suite, schema riêng cho từng worker hoặc fixture theo transaction nếu công nghệ hỗ trợ. Cần bảo đảm các biện pháp này không làm giảm tính độc lập hoặc che giấu hành vi tích hợp cần kiểm tra.

### 3.3. Ngân sách cho các nhóm rộng hơn

End-to-end, kiểm thử tải và kiểm thử phục hồi thường cần môi trường và thời gian dài hơn. Chúng không nên bị ép vào ngân sách unit hoặc integration. Hãy đặt lịch, điều kiện thực thi và tiêu chí dừng riêng, đồng thời bảo đảm những rủi ro quan trọng vẫn có phản hồi đủ sớm trước phát hành.

## 4. Cách xác lập ngân sách có căn cứ

Không nên chọn một con số chỉ vì một dự án khác đã dùng. Hãy dùng dữ liệu hiện tại và mục tiêu phản hồi để xác định ngân sách.

### 4.1. Đo đường cơ sở

Trước tiên, thu thập thời gian của nhiều lần chạy trong điều kiện đại diện. Ghi nhận:

- Tổng số test và số test được thực thi thực tế.
- Thời gian tổng và thời gian của từng nhóm.
- Thời gian setup, execution, teardown và reporting.
- Số worker hoặc runner chạy song song.
- Tỷ lệ test retry, timeout, flaky hoặc bị bỏ qua.
- Cấu hình máy, tài nguyên, phiên bản runtime và dịch vụ phụ thuộc.

Không nên dùng một lần chạy nhanh nhất làm đường cơ sở. Hãy xem xét xu hướng, phân vị hoặc các lần chạy ổn định để hiểu biến động. Một lần chạy chậm do runner bị tranh chấp tài nguyên không nên tự động được coi là hiệu năng bình thường của suite.

### 4.2. Xác định nhu cầu phản hồi

Hỏi nhóm phát triển và vận hành:

- Người phát triển cần kết quả nào trước khi tiếp tục chỉnh sửa?
- Pipeline cần phản hồi trong bao lâu để không làm chậm quá trình review hoặc hợp nhất?
- Kiểm thử nào cần chạy trên mỗi commit, mỗi pull request, theo lịch hoặc trước phát hành?
- Nhóm có thể sử dụng bao nhiêu runner và tài nguyên môi trường?
- Rủi ro nào yêu cầu kiểm tra ngay cả khi thời gian chạy dài hơn?

Ngân sách cần cân bằng tốc độ với mức bảo vệ. Không cắt bỏ kiểm thử quan trọng chỉ để đạt một con số thời gian đẹp.

### 4.3. Chia ngân sách thành phần

Ví dụ minh họa cho một pipeline:

| Giai đoạn | Ngân sách mục tiêu minh họa | Ghi chú |
|---|---:|---|
| Unit test | 3 phút | Chạy thường xuyên trên thay đổi mã. |
| Component và contract test | 5 phút | Dùng fixture và phụ thuộc nhẹ. |
| Integration test | 10 phút | Bao gồm khởi tạo phụ thuộc và dọn dữ liệu. |
| Smoke / end-to-end đại diện | 8 phút | Chạy ở giai đoạn sau build hoặc trước phát hành. |
| Tổng thời gian phản hồi | 26 phút | Mục tiêu giả định, chưa tính thời gian chờ runner. |

Các số trên chỉ minh họa cách chia. Dự án thực tế cần đo đường cơ sở, xác định yêu cầu phản hồi và hiệu chỉnh theo tài nguyên. Nếu tổng ngân sách không thể đạt trong môi trường hiện tại, cần xem xét song song hóa, chia suite, tối ưu setup hoặc thay đổi lịch chạy; không nên tùy tiện hạ phạm vi kiểm tra.

### 4.4. Dùng percentile và xu hướng

Thời gian chạy có thể dao động. Trung bình có thể che khuất những lần chạy rất chậm, còn giá trị nhỏ nhất không phản ánh trải nghiệm thường gặp. Có thể theo dõi p50, p90 hoặc p95 của thời gian suite, cùng số mẫu và điều kiện đo.

Ví dụ, nếu p50 của integration suite là 7 phút nhưng p95 là 18 phút, cần tìm hiểu các lần chạy chậm: khởi động database, tranh chấp runner, retry, truy vấn không ổn định hay tác vụ nền. Ngân sách cần dựa trên mức phản hồi nhóm muốn cam kết, đồng thời có ngưỡng cảnh báo khi xu hướng xấu đi.

## 5. Tiêu chí độc lập của một test

Một test độc lập phải có thể thực thi và cho cùng kết quả khi được chạy:

- Một mình, không cần chạy test khác trước đó.
- Lặp lại nhiều lần trong cùng điều kiện.
- Trước hoặc sau test khác mà không phụ thuộc thứ tự.
- Trong một suite lớn hoặc trong một nhóm nhỏ được chọn lọc.
- Song song với test khác, nếu tài nguyên được phân vùng đúng.
- Trên runner sạch hoặc môi trường được chuẩn bị theo quy trình đã mô tả.

Tính độc lập không có nghĩa test không được dùng chung bất kỳ thành phần nào. Nhiều test có thể dùng chung một binary, image container hoặc dịch vụ nền nếu chúng không chia sẻ trạng thái có thể làm thay đổi kết quả. Cần phân biệt tài nguyên bất biến có thể dùng chung với trạng thái mutable phải được cô lập.

### 5.1. Các tiêu chí cụ thể

| Tiêu chí | Ý nghĩa | Dấu hiệu vi phạm |
|---|---|---|
| Tự chuẩn bị | Test tạo hoặc khai báo trạng thái cần thiết trước khi kiểm tra. | Chỉ Pass sau khi một test khác tạo dữ liệu. |
| Tự xác minh | Test kiểm tra kết quả của chính nó bằng assertion rõ ràng. | Dựa vào log hoặc assertion của test khác. |
| Không phụ thuộc thứ tự | Kết quả không đổi khi đảo thứ tự chạy. | Chạy cả suite thì Pass, chạy riêng thì Fail. |
| Có thể lặp lại | Cùng điều kiện và đầu vào cho kết quả nhất quán. | Kết quả phụ thuộc thời gian, dữ liệu ngẫu nhiên không kiểm soát hoặc trạng thái còn sót. |
| Cô lập trạng thái | Test không làm thay đổi trạng thái khiến test khác bị ảnh hưởng. | Dùng chung bản ghi, file, queue hoặc biến toàn cục có thể ghi. |
| An toàn khi chạy song song | Test không tranh chấp tài nguyên mutable ngoài phạm vi đã cô lập. | Flaky khi tăng số worker hoặc chạy cùng suite khác. |
| Dọn dẹp có kiểm soát | Tài nguyên được giải phóng hoặc reset mà không ảnh hưởng test khác. | Dữ liệu tích tụ, port bị chiếm hoặc test xóa dữ liệu của worker khác. |
| Kết quả có thể chẩn đoán | Khi thất bại, có đủ thông tin để xác định điều kiện và nguyên nhân. | Chỉ có lỗi timeout chung, không có ID, log hoặc trạng thái cần thiết. |

## 6. Cô lập dữ liệu và trạng thái

Nguồn phụ thuộc thường gặp nhất giữa các test là trạng thái có thể thay đổi: bản ghi database, file, biến môi trường, cache, hàng đợi, tài khoản dùng chung hoặc dữ liệu tĩnh có thể bị ghi.

### 6.1. Tạo dữ liệu riêng cho từng test

Ưu tiên dữ liệu có định danh riêng theo test hoặc lần chạy. Ví dụ, thay vì mọi test cùng sử dụng một tài khoản `user@example.test`, mỗi test có thể tạo một người dùng riêng với mã định danh gắn với test ID hoặc run ID.

```java
@Test
void createsOrderForCurrentCustomer() {
    Customer customer = customerFixture.createUniqueCustomer();
    Product product = productFixture.createAvailableProduct();

    Order order = orderService.createOrder(customer.id(), product.id(), 2);

    assertEquals(customer.id(), order.customerId());
    assertEquals(2, order.items().get(0).quantity());
}
```

Ví dụ trên giả định fixture tạo dữ liệu riêng cho test. Trong dự án thực tế, cần bảo đảm fixture không phụ thuộc vào dữ liệu do test khác tạo và có cơ chế dọn dữ liệu phù hợp.

### 6.2. Dùng transaction hoặc database riêng khi phù hợp

Transaction rollback có thể giúp dọn dữ liệu sau test, nhưng chỉ hiệu quả khi toàn bộ thao tác nằm trong transaction được quản lý và không có side effect bên ngoài transaction. Nếu ứng dụng phát thông điệp ra broker, gọi dịch vụ ngoài hoặc mở transaction riêng, rollback database không tự hoàn tác những tác động đó.

Database hoặc schema riêng cho từng worker có thể giúp chạy song song an toàn. Nếu dùng chung database, cần phân vùng dữ liệu, tránh khóa hoặc xóa dữ liệu ngoài phạm vi và không dùng các ID cố định có thể xung đột.

### 6.3. Dọn dẹp không được phá trạng thái của test khác

Cleanup cần giới hạn theo tài nguyên mà test sở hữu. Tránh lệnh xóa toàn bộ bảng hoặc reset toàn bộ môi trường sau mỗi test nếu suite khác có thể đang sử dụng cùng môi trường. Nếu cần reset toàn bộ, thực hiện ở ranh giới suite hoặc môi trường cô lập và bảo đảm không có tiến trình khác phụ thuộc.

## 7. Loại bỏ phụ thuộc vào thời gian và tính ngẫu nhiên

Test có thể không ổn định nếu phụ thuộc vào đồng hồ thật, độ trễ mạng, thứ tự thread hoặc dữ liệu ngẫu nhiên không kiểm soát.

### 7.1. Không dùng sleep như cơ chế đồng bộ mặc định

Một đoạn `Thread.sleep(5000)` chỉ trì hoãn test; nó không chứng minh sự kiện cần thiết đã xảy ra. Trên máy nhanh, test chờ thừa; trên máy chậm, 5 giây vẫn không đủ. Hãy chờ điều kiện có thể quan sát được với timeout hữu hạn.

```java
await().atMost(Duration.ofSeconds(5))
       .untilAsserted(() ->
           assertEquals("COMPLETED", orderRepository.findStatus(orderId))
       );
```

Ví dụ dùng một cơ chế polling có timeout. Trong dự án thực tế, cần chọn khoảng polling hợp lý và bảo đảm truy vấn trạng thái không gây tải quá mức.

### 7.2. Kiểm soát đồng hồ

Với logic phụ thuộc thời gian, hãy tiêm clock hoặc abstraction thời gian để test có thể điều khiển thời điểm hiện tại. Điều này giúp kiểm tra token hết hạn, thời hạn đặt hàng hoặc lịch xử lý mà không phải chờ thời gian thật.

```java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-01-15T10:00:00Z"),
    ZoneOffset.UTC
);

ExpiryPolicy policy = new ExpiryPolicy(fixedClock);
assertTrue(policy.isValid(Instant.parse("2026-01-15T10:05:00Z")));
```

Test cần xác định rõ múi giờ, thời điểm biên và cách so sánh trước/sau hạn. Không nên dựa vào giờ máy của runner nếu logic yêu cầu thời điểm chính xác.

### 7.3. Kiểm soát dữ liệu ngẫu nhiên

Random test hoặc property-based test có thể khám phá nhiều đầu vào, nhưng cần lưu seed hoặc đầu vào thất bại để tái hiện. Không nên để test tạo dữ liệu ngẫu nhiên mà không ghi lại cách tái tạo. Nếu dùng UUID, hãy bảo đảm nó chỉ dùng để định danh dữ liệu chứ không làm kết quả mong đợi trở nên không xác định.

### 7.4. Tránh phụ thuộc môi trường không khai báo

Test không nên ngầm dựa vào locale, timezone, thứ tự file, port cố định, biến môi trường cá nhân hoặc trạng thái dịch vụ trên máy của một lập trình viên. Khai báo cấu hình cần thiết và chuẩn bị môi trường nhất quán trong pipeline.

## 8. Tính độc lập ở từng nhóm kiểm thử

Các nhóm có cách cô lập khác nhau. Cần định nghĩa tiêu chí riêng thay vì yêu cầu mọi nhóm phải dùng cùng một phương pháp.

### 8.1. Unit test

- Mỗi test tạo đầu vào và dependency cần thiết.
- Không gọi mạng hoặc dịch vụ thật nếu mục tiêu là kiểm tra logic đơn vị.
- Không dựa vào thứ tự khai báo hoặc thứ tự chạy.
- Không sửa biến static hoặc singleton dùng chung mà không khôi phục an toàn.
- Không chia sẻ mock có trạng thái giữa các test.
- Có thể chạy riêng và chạy song song mà không tranh chấp tài nguyên.

### 8.2. Component test

- Thành phần được khởi tạo với cấu hình xác định.
- Phụ thuộc ngoài ranh giới được thay thế có chủ đích hoặc được cấp riêng.
- Dữ liệu khởi tạo thuộc phạm vi của test hoặc suite.
- Test kiểm tra hành vi qua giao diện thành phần, tránh phụ thuộc chi tiết nội bộ dễ thay đổi.
- Việc dọn dẹp không ảnh hưởng đến component test khác.

### 8.3. Contract test

- Hợp đồng và phiên bản provider được xác định rõ.
- Mỗi tương tác kiểm tra được độc lập hoặc dữ liệu hợp đồng không phụ thuộc trạng thái do tương tác trước tạo.
- Kết quả xác minh có thể truy nguyên đến phiên bản hợp đồng và provider.
- Nếu provider verification cần môi trường dùng chung, dữ liệu và trạng thái phải được cô lập.
- Thay đổi hợp đồng phải tạo kết quả rõ ràng, không phụ thuộc cache cũ hoặc artifact chưa cập nhật.

### 8.4. Integration test

- Phụ thuộc thật được khởi tạo hoặc chọn phiên bản rõ ràng.
- Dữ liệu và namespace được phân vùng theo test, suite hoặc worker.
- Test không dựa vào trạng thái còn lại từ lần chạy trước.
- Các sự kiện bất đồng bộ được chờ bằng điều kiện và timeout xác định.
- Cleanup chỉ xóa tài nguyên do test sở hữu.
- Có thể chạy test riêng, lặp lại và song song trong giới hạn tài nguyên đã thiết kế.

### 8.5. End-to-end test

- Hành trình có thể bắt đầu từ trạng thái ban đầu đã biết.
- Tài khoản, dữ liệu và tenant được cấp riêng hoặc được đặt lại có kiểm soát.
- Test không phụ thuộc vào một hành trình khác đã chạy trước đó.
- Side effect như email, SMS hoặc thanh toán được chuyển đến sandbox hoặc hộp thư kiểm thử.
- Có thể xác định và dọn trạng thái cuối mà không ảnh hưởng người dùng hoặc suite khác.

Một end-to-end test có thể không hoàn toàn độc lập với hạ tầng dùng chung, nhưng giới hạn phụ thuộc cần được công bố và kiểm soát. Không nên coi một test flaky do môi trường là test độc lập chỉ vì nó thường Pass khi chạy toàn suite.

## 9. Phân nhóm test và tổ chức pipeline

Để ngân sách có ý nghĩa, nhóm cần định nghĩa rõ các nhóm test được chạy ở đâu và khi nào. Có thể dùng tag, package, source set hoặc cấu hình build để tách nhóm.

Ví dụ phân nhóm:

| Nhóm | Trigger thường dùng | Mục tiêu phản hồi |
|---|---|---|
| Unit | Mỗi thay đổi mã hoặc commit | Phát hiện nhanh lỗi logic và quy tắc. |
| Component / contract | Pull request hoặc khi thành phần/hợp đồng thay đổi | Phát hiện sai lệch trong thành phần và giao diện. |
| Integration | Pull request, build chính hoặc lịch phù hợp | Xác minh tương tác với phụ thuộc thật. |
| System / end-to-end | Sau build tích hợp hoặc trước phát hành | Xác minh hành trình đại diện. |
| Performance / resilience | Theo lịch, trước mốc phát hành hoặc sau thay đổi hạ tầng | Đánh giá mục tiêu tải và khả năng phục hồi. |

Ví dụ cấu hình JUnit có thể dùng tag để chọn nhóm:

```java
@Tag("unit")
class PriceCalculatorTest {
    // Kiểm tra logic tính giá trong phạm vi đơn vị.
}

@Tag("integration")
class OrderRepositoryIT {
    // Kiểm tra tương tác với database kiểm thử.
}
```

Ví dụ lệnh chạy (tùy cấu hình build của dự án):

```bash
./gradlew test
./gradlew integrationTest
```

Task `integrationTest` thường cần được khai báo riêng trong cấu hình Gradle. Với JUnit 5, việc lọc `@Tag` cần được cấu hình qua `useJUnitPlatform` hoặc một task riêng; tham số `-Dgroups` không tự động lọc tag trong mọi cấu hình. Hãy dùng đúng task và cơ chế lọc đã được khai báo trong dự án.

Pipeline có thể chạy các nhóm song song nếu tài nguyên và dữ liệu đã được cô lập. Nếu integration suite dùng chung một database hoặc một tenant, chạy song song có thể làm tăng tốc độ nhưng giảm độ tin cậy. Cần giải quyết cô lập trước khi tăng số worker.

## 10. Timeout, retry và xử lý test chậm

Timeout giúp ngăn một test giữ runner vô hạn, nhưng timeout không thay thế việc xác định nguyên nhân chậm. Một test có timeout quá dài có thể làm pipeline bị treo; timeout quá ngắn có thể gây lỗi giả trên runner chịu tải.

### 10.1. Đặt timeout theo loại thao tác

- Logic thuần thường không cần timeout riêng ở từng test nếu suite đã được giám sát.
- I/O, database và HTTP cần timeout phù hợp với hợp đồng và môi trường.
- Kiểm thử bất đồng bộ cần timeout chờ trạng thái cuối, không chờ vô hạn.
- Kiểm thử tải cần thời gian warm-up, đo và cooldown được xác định trước.

Timeout của một thao tác nên nhỏ hơn hoặc bằng giới hạn tổng của test và suite, có xét đến thời gian cleanup. Nếu mỗi lớp đặt timeout lớn độc lập, tổng thời gian thất bại có thể vượt ngân sách nhiều lần.

### 10.2. Không dùng retry để che flaky test

Retry có thể hữu ích khi kiểm tra một lỗi tạm thời của hệ thống thật, nhưng tự động chạy lại một test thất bại rồi chỉ báo kết quả cuối cùng là Pass sẽ che khuất sự không ổn định. Nếu cần retry, hãy ghi lại lần thất bại đầu tiên, số lần thử, nguyên nhân và trạng thái cuối. Theo dõi tỷ lệ retry như một chỉ số chất lượng suite.

### 10.3. Phân loại test chậm

Khi một test vượt ngân sách, hãy xác định nó thuộc nhóm nào:

- Setup tốn thời gian do khởi động môi trường hoặc tạo dữ liệu.
- Execution tốn thời gian do truy vấn, thuật toán hoặc I/O.
- Chờ bất đồng bộ không hiệu quả.
- Teardown hoặc cleanup chậm.
- Chờ tài nguyên runner hoặc phụ thuộc dùng chung.
- Test đang thực hiện quá nhiều hành vi và cần tách phạm vi.

Chỉ sau khi xác định nguyên nhân mới chọn cách tối ưu như giảm fixture, tái sử dụng môi trường bất biến, chia suite, song song hóa hoặc sửa truy vấn. Tránh tăng ngân sách một cách tự động mỗi khi test chậm.

## 11. Chạy song song mà vẫn độc lập

Chạy song song có thể giảm thời gian tổng nhưng chỉ an toàn khi test không tranh chấp trạng thái mutable.

### 11.1. Các tài nguyên cần phân vùng

- Database, schema, tenant và bản ghi.
- File tạm, thư mục output và tên file.
- Port, socket và tiến trình server.
- Queue, topic, subscription và consumer group.
- Tài khoản, token và session.
- Cache key và khóa phân tán.
- Tên bucket, object và tài nguyên cloud.

Có thể tạo namespace theo `runId`, `workerId` hoặc `testId` để tránh xung đột. Với port, ưu tiên cấp port động hoặc cơ chế server hỗ trợ chọn cổng trống. Với file, tạo thư mục tạm riêng và xóa đúng thư mục thuộc test.

### 11.2. Tài nguyên dùng chung an toàn

Một số tài nguyên có thể dùng chung nếu bất biến hoặc được đồng bộ đúng cách, ví dụ image container, schema hợp đồng chỉ đọc hoặc artifact build. Tuy nhiên, cache có thể thay đổi, cấu hình có thể bị cập nhật và dữ liệu seed có thể bị sửa. Cần phân loại tài nguyên trước khi dùng chung.

### 11.3. Giới hạn mức song song

Không phải lúc nào tăng worker cũng làm suite nhanh hơn. Khi database, CPU, bộ nhớ hoặc dịch vụ phụ thuộc đạt giới hạn, thêm worker có thể làm thời gian từng test tăng, timeout nhiều hơn và kết quả khó ổn định. Hãy đo thời gian tổng cùng mức sử dụng tài nguyên để tìm điểm song song hiệu quả.

## 12. Phát hiện và sửa test phụ thuộc thứ tự

Test phụ thuộc thứ tự thường biểu hiện bằng việc chạy cả suite thì Pass nhưng chạy riêng hoặc đảo thứ tự thì Fail.

Các nguyên nhân phổ biến:

- Test trước tạo dữ liệu mà test sau ngầm sử dụng.
- Test sửa cấu hình toàn cục nhưng không khôi phục.
- Test dùng chung mock hoặc singleton có trạng thái.
- Test không dọn queue, cache, file hoặc database.
- Test giả định đồng hồ, timezone hoặc locale của máy.
- Test chạy nền nhưng không chờ hoặc không dừng tiến trình.
- Test phụ thuộc vào thứ tự dữ liệu trả về khi truy vấn không có `ORDER BY`.

### 12.1. Cách tìm lỗi

1. Chạy test thất bại một mình trên môi trường sạch.
2. Chạy test nhiều lần để xem kết quả có thay đổi không.
3. Chạy test trước và sau các test nghi ngờ để xác định trạng thái gây ảnh hưởng.
4. Đảo thứ tự hoặc xáo trộn thứ tự chạy nếu framework hỗ trợ.
5. Chạy với số worker khác nhau để phát hiện tranh chấp tài nguyên.
6. Ghi log setup, dữ liệu, thời điểm, thread và tài nguyên liên quan.

### 12.2. Cách sửa

- Tạo dữ liệu cần thiết ngay trong test.
- Dùng dependency injection thay vì biến toàn cục có trạng thái.
- Reset hoặc cô lập trạng thái trước và sau test.
- Dùng transaction hoặc namespace riêng khi phù hợp.
- Chờ điều kiện rõ ràng và dừng tiến trình nền.
- Sắp xếp kết quả truy vấn một cách tường minh nếu thứ tự là một phần của kết quả mong đợi.
- Chuyển các hành vi phụ thuộc môi trường sang integration test có setup được quản lý.

Không nên sửa bằng cách ép test luôn chạy theo một thứ tự cố định nếu thứ tự đó không phải là một phần của hành vi sản phẩm. Cách này chỉ che giấu phụ thuộc và làm suite khó mở rộng.

## 13. Theo dõi ngân sách và tính độc lập

Nhóm cần theo dõi các chỉ số giúp nhận biết ngân sách bị tiêu thụ và chất lượng độc lập suy giảm.

| Chỉ số | Điều cần quan sát | Dấu hiệu cần điều tra |
|---|---|---|
| Tổng thời gian suite | Thời gian thực tế so với ngân sách | Xu hướng tăng qua các lần build. |
| Thời gian theo test hoặc nhóm | Các test và nhóm chậm nhất | Một test đơn lẻ chiếm phần lớn ngân sách. |
| Setup và teardown | Tỷ lệ thời gian môi trường so với thực thi | Khởi tạo hoặc cleanup chiếm phần lớn thời gian. |
| Flaky rate | Số lần kết quả không ổn định | Tăng retry hoặc kết quả khác nhau giữa runner. |
| Order-dependence | Kết quả khi chạy riêng, đảo thứ tự và chạy toàn suite | Test chỉ Pass khi có test khác chạy trước. |
| Parallel safety | Kết quả khi tăng worker | Lỗi xung đột dữ liệu, port hoặc tài nguyên. |
| Queue time | Thời gian chờ runner và môi trường | Người phát triển chờ lâu dù suite thực thi nhanh. |
| Failure diagnosis time | Thời gian tìm nguyên nhân khi test thất bại | Log thiếu ngữ cảnh hoặc test có quá nhiều trách nhiệm. |

Nên theo dõi xu hướng và phân vị thay vì chỉ nhìn một lần chạy. Khi ngân sách bị vượt, báo cáo cần chỉ rõ nhóm nào, thành phần thời gian nào và nguyên nhân đã biết hoặc chưa biết.

## 14. Ví dụ thực tế: ngân sách và tính độc lập cho Order service

Giả sử Order service có unit test cho quy tắc tính giá, component test cho xử lý đơn hàng, contract test với Payment service và integration test với database cùng message broker.

### 14.1. Ngân sách minh họa

| Nhóm | Mục tiêu thời gian | Cách kiểm soát |
|---|---:|---|
| Unit | 2 phút | Không truy cập mạng; fixture nhẹ; theo dõi test chậm. |
| Component | 4 phút | Khởi tạo service một lần cho suite, dữ liệu riêng theo test. |
| Contract | 3 phút | Artifact hợp đồng có phiên bản; provider verification được tách rõ. |
| Integration | 8 phút | Container database và broker; setup, execution, cleanup được đo riêng. |

Đây là ngân sách ví dụ cho một dự án giả định. Nếu số lượng test, tài nguyên CI hoặc độ phức tạp khác, nhóm cần đo và đặt mục tiêu mới.

### 14.2. Tiêu chí độc lập

- Mỗi unit test tự tạo customer, product và dữ liệu giá cần thiết.
- Component test dùng namespace hoặc transaction riêng và không dựa vào đơn hàng từ test khác.
- Contract test dùng schema và phiên bản provider xác định, không phụ thuộc cache hợp đồng cũ.
- Integration test tạo dữ liệu đơn hàng có ID riêng, kiểm tra trạng thái database và thông điệp được phát ra.
- Cleanup chỉ xóa dữ liệu của lần chạy hiện tại.
- Khi chạy song song, mỗi worker có namespace riêng cho database và queue.

### 14.3. Một lỗi phụ thuộc thứ tự

Giả sử `createsOrder` tạo một khách hàng có email cố định và không xóa sau test. Test `rejectsDuplicateEmail` giả định email đó chưa tồn tại. Khi chạy riêng, test thứ hai Pass; khi chạy cả suite sau `createsOrder`, nó Fail.

Cách sửa là mỗi test tạo email duy nhất hoặc dùng fixture riêng, đồng thời dọn dữ liệu do test tạo. Không nên buộc `rejectsDuplicateEmail` chạy trước `createsOrder`, vì thứ tự không phải điều kiện của nghiệp vụ.

### 14.4. Một suite vượt ngân sách

Giả sử integration suite tăng từ 8 lên 17 phút. Đo chi tiết cho thấy 6 phút nằm ở khởi động broker và database, 2 phút ở migration, còn lại ở thực thi và cleanup. Nhóm có thể xem xét tái sử dụng container cho một lần chạy suite, chạy migration một lần trên database cô lập, chia test theo ranh giới hoặc cải thiện truy vấn. Sau thay đổi, cần kiểm tra lại tính độc lập và an toàn khi chạy song song.

## 15. Quy trình thiết lập và duy trì ngân sách

Nhóm có thể áp dụng quy trình sau:

1. **Phân loại nhóm test**: xác định unit, component, contract, integration và nhóm rộng hơn theo phạm vi thực tế.
2. **Đo đường cơ sở**: ghi thời gian tổng, từng giai đoạn, thời gian chờ runner và biến động giữa các lần chạy.
3. **Xác định mục tiêu phản hồi**: thống nhất thời gian cần có kết quả theo từng trigger trong pipeline.
4. **Đặt ngân sách thành phần**: chia ngân sách cho setup, execution, teardown và reporting; ghi rõ ngưỡng cảnh báo.
5. **Định nghĩa tiêu chí độc lập**: xác định cách chuẩn bị dữ liệu, cô lập trạng thái, đồng hồ, tài nguyên và cleanup.
6. **Kiểm tra độc lập**: chạy riêng, lặp lại, đảo thứ tự và chạy song song với mức worker đại diện.
7. **Tổ chức pipeline**: đặt nhóm test ở giai đoạn phù hợp, ưu tiên phản hồi nhanh nhưng vẫn bảo vệ rủi ro quan trọng.
8. **Theo dõi và tối ưu**: phân tích test chậm, flaky, queue time và tranh chấp tài nguyên trước khi thay đổi ngân sách.
9. **Rà soát định kỳ**: cập nhật ngân sách khi số lượng test, kiến trúc, hạ tầng hoặc nhu cầu phản hồi thay đổi.

## 16. Tự kiểm tra

Trước khi đưa một nhóm test vào pipeline, hãy tự hỏi:

- Nhóm test có mục tiêu và ngân sách thời gian rõ ràng không?
- Điểm bắt đầu và kết thúc phép đo đã được thống nhất chưa?
- Đã tách thời gian setup, execution, teardown và queueing chưa?
- Ngân sách có căn cứ từ dữ liệu thực tế và nhu cầu phản hồi không?
- Mỗi test có thể chạy riêng và tự chuẩn bị dữ liệu cần thiết không?
- Kết quả có ổn định khi lặp lại và đảo thứ tự không?
- Dữ liệu, file, queue, port và tài nguyên mutable có được cô lập không?
- Cleanup có giới hạn đúng tài nguyên do test sở hữu không?
- Nhóm có thể chạy song song trong giới hạn tài nguyên đã thiết kế không?
- Timeout và retry có giúp chẩn đoán thay vì che giấu lỗi không?
- Khi vượt ngân sách, nhóm có thể xác định thành phần thời gian và nguyên nhân không?

## Kết luận

Ngân sách thời gian giúp mỗi nhóm kiểm thử cung cấp phản hồi trong khoảng phù hợp với vai trò của nó; tiêu chí độc lập bảo đảm kết quả không phụ thuộc thứ tự, trạng thái còn sót hoặc test khác. Unit test cần phản hồi nhanh và cô lập logic; component, contract và integration test cần ngân sách riêng cho môi trường, dữ liệu và tương tác thật. Khi đo thời gian theo từng thành phần, cô lập trạng thái, kiểm tra khả năng lặp lại và theo dõi xu hướng, nhóm có thể giữ pipeline nhanh mà vẫn duy trì bằng chứng kiểm thử đáng tin cậy.
