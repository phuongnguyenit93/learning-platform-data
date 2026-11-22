# Tương thích hành vi: giữ hợp đồng và kết quả quan sát được

Trong một cuộc migration Java, thay thế thư viện, framework, phiên bản JDK hoặc cách triển khai thường không khó ở chỗ làm cho mã mới chạy được. Thách thức lớn hơn là bảo đảm các thành phần đang sử dụng hệ thống vẫn nhận được hành vi mà chúng đã dựa vào. Một phương thức vẫn giữ nguyên tên và kiểu trả về nhưng đổi thứ tự phần tử, cách xử lý `null`, loại exception hoặc quy tắc làm tròn vẫn có thể làm hỏng ứng dụng ở phía gọi.

**Tương thích hành vi (behavioral compatibility)** là khả năng một phiên bản hoặc cách triển khai mới tiếp tục đáp ứng hợp đồng hành vi mà consumer đang quan sát và sử dụng. Consumer có thể là một lớp Java gọi phương thức, một module khác, một tiến trình qua REST, một job đọc dữ liệu, hoặc một hệ thống bên ngoài. Khi thay đổi nội bộ mà consumer vẫn nhận được kết quả và hiệu ứng được cam kết như trước, thay đổi đó giữ được tương thích hành vi.

Trọng tâm của loại tương thích này là hợp đồng ở ranh giới giữa producer và consumer: đầu vào nào được chấp nhận, đầu ra có ý nghĩa gì, trạng thái thay đổi ra sao, lỗi được biểu diễn thế nào và các hiệu ứng bên ngoài xuất hiện theo thứ tự nào. Mục tiêu không phải giữ nguyên từng dòng code, mà là giữ nguyên những điều consumer có quyền dựa vào.

## 1. Hành vi được quan sát từ phía consumer

Một triển khai có thể được thay đổi rất nhiều mà không làm thay đổi hành vi bên ngoài. Ví dụ, có thể thay vòng lặp bằng Stream API, thay cấu trúc dữ liệu nội bộ, tách một lớp thành nhiều service hoặc chuyển cách truy vấn từ JDBC sang một thư viện persistence khác. Nếu các consumer vẫn nhận cùng kết quả theo hợp đồng, đây thường là thay đổi tương thích hành vi.

Ngược lại, thay đổi nhỏ trong code có thể tạo ra khác biệt lớn ở ranh giới sử dụng:

- Một API trước đây trả về danh sách rỗng khi không có dữ liệu, nay trả về `null`.
- Một phương thức trước đây giữ thứ tự đầu vào, nay trả kết quả theo thứ tự không xác định do dùng `HashSet`.
- Một phép tính tài chính đổi quy tắc làm tròn nên chỉ khác ở một số giá trị sát ngưỡng.
- Một thao tác trước đây ném `AccountNotFoundException`, nay trả về đối tượng mặc định khiến consumer tưởng tài khoản tồn tại.
- Một hàm trước đây không sửa collection đầu vào, nay sắp xếp trực tiếp collection đó.
- Một endpoint trước đây trả mã HTTP `404` cho tài nguyên không tồn tại, nay trả `200` với body rỗng.

Trong từng trường hợp, code mới có thể biên dịch và chạy bình thường. Vấn đề chỉ xuất hiện khi consumer dựa vào khác biệt hành vi đó để quyết định bước tiếp theo.

### 1.1. Hợp đồng là điều consumer có thể dựa vào

Hợp đồng hành vi mô tả quan hệ giữa đầu vào, trạng thái và kết quả. Có thể phân tích một hợp đồng theo các phần sau:

| Thành phần | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Tiền điều kiện | Đầu vào nào hợp lệ? | `customerId` không được `null`; số tiền phải không âm |
| Hậu điều kiện | Khi thành công, kết quả có ý nghĩa gì? | Chỉ trả về đơn hàng đang mở của khách hàng |
| Bất biến | Điều gì luôn phải đúng trước và sau thao tác? | Số dư không được âm nếu tài khoản không hỗ trợ thấu chi |
| Trạng thái | Dữ liệu nào được tạo, sửa hoặc xóa? | Đơn hàng chuyển từ `PENDING` sang `CONFIRMED` |
| Hiệu ứng phụ | Hệ thống bên ngoài bị tác động thế nào? | Gửi một sự kiện sau khi giao dịch commit |
| Lỗi | Trường hợp thất bại được biểu diễn ra sao? | Ném `OrderNotFoundException` khi không tìm thấy đơn hàng |
| Thứ tự và tính ổn định | Kết quả hoặc hiệu ứng có thứ tự xác định không? | Danh sách được sắp theo thời điểm tạo tăng dần |
| Tính lặp lại | Gọi lại cùng thao tác có tạo thêm tác động không? | Gửi lại request cùng idempotency key không tạo giao dịch thứ hai |

Không phải mọi chi tiết đều cần được cam kết. Một hợp đồng tốt phân biệt rõ điều consumer được phép dựa vào với chi tiết triển khai có thể thay đổi. Ví dụ, hợp đồng có thể cam kết kết quả được sắp theo `createdAt`, nhưng không cần cam kết hệ thống dùng `ArrayList`, `LinkedList` hay câu SQL cụ thể.

### 1.2. Kết quả quan sát được rộng hơn giá trị trả về

Khi đánh giá tương thích hành vi, chỉ so sánh giá trị trả về là chưa đủ. Consumer có thể quan sát nhiều khía cạnh khác:

- **Giá trị và cấu trúc dữ liệu:** nội dung, kiểu dữ liệu, định dạng, độ chính xác, đơn vị đo và cách biểu diễn giá trị vắng mặt.
- **Thứ tự:** thứ tự phần tử trong collection, thứ tự sự kiện, thứ tự callback hoặc thứ tự xử lý các bản ghi.
- **Tính khả biến:** collection trả về có sửa được không; đối tượng đầu vào có bị thay đổi không; kết quả có phải bản sao độc lập không.
- **Lỗi:** loại exception, mã lỗi, HTTP status, thông tin lỗi và thời điểm lỗi xảy ra.
- **Trạng thái và hiệu ứng phụ:** bản ghi được ghi, message được phát, file được tạo, transaction được commit hoặc rollback.
- **Thời gian và đồng thời:** timeout, khả năng nhìn thấy dữ liệu sau commit, thứ tự cạnh tranh giữa các thao tác và giới hạn tài nguyên đã cam kết.
- **Giao tiếp:** tên header, schema JSON, encoding, thứ tự trường nếu consumer phụ thuộc, quy tắc retry và semantics của giao thức.

Hiệu năng cũng có thể trở thành một phần của hợp đồng khi hệ thống công bố hoặc phụ thuộc vào một giới hạn cụ thể, chẳng hạn API phải phản hồi trong một ngưỡng SLA. Tuy vậy, không nên mặc định mọi thay đổi vài mili giây đều là phá vỡ tương thích. Cần xác định rõ giới hạn nào là cam kết vận hành và consumer nào phụ thuộc vào nó.

## 2. Phân biệt tương thích hành vi với các loại tương thích khác

Các loại tương thích thường liên quan nhưng kiểm tra những câu hỏi khác nhau. Một thay đổi có thể vượt qua kiểm tra biên dịch nhưng vẫn phá vỡ hành vi lúc chạy.

| Loại tương thích | Câu hỏi chính | Ví dụ thay đổi có thể gây lỗi |
|---|---|---|
| Source compatibility | Mã nguồn consumer có biên dịch với API mới không? | Xóa overload mà consumer đang gọi |
| Binary compatibility | Bytecode đã biên dịch có liên kết và chạy với thư viện mới không? | Xóa method descriptor mà bytecode cũ tham chiếu |
| API compatibility | Bề mặt API công khai có được duy trì không? | Đổi tên public class hoặc thay chữ ký method |
| Protocol/data compatibility | Hai phía có tiếp tục hiểu cùng giao thức và dữ liệu không? | Đổi tên JSON field hoặc thay ý nghĩa enum |
| Behavioral compatibility | Consumer có tiếp tục nhận hành vi theo hợp đồng không? | Giữ chữ ký method nhưng đổi kết quả hoặc exception |

Ví dụ, method `getUsers()` vẫn tồn tại với chữ ký `List<User> getUsers()`, nên source và binary compatibility có thể được giữ. Nhưng nếu bản mới loại bỏ user trùng lặp, thay thứ tự danh sách hoặc trả collection không thể sửa trong khi hợp đồng cũ cho phép sửa, consumer vẫn có thể hỏng. Các công cụ kiểm tra API hay binary compatibility không tự phát hiện đầy đủ những khác biệt như vậy.

Tương thích hành vi cũng không đồng nghĩa với việc mọi hành vi cũ đều phải tồn tại mãi mãi. Một sản phẩm có thể chủ động sửa bug hoặc thay đổi semantics, nhưng khi đó cần nhận diện đây là thay đổi hợp đồng, đánh giá consumer bị ảnh hưởng và cung cấp lộ trình chuyển đổi phù hợp.

## 3. Ví dụ Java: thay cách triển khai nhưng giữ semantics

Giả sử một service cung cấp phương thức lấy tên của các user đang hoạt động:

```java
public List<String> findActiveNames(List<User> users) {
    if (users == null) {
        throw new IllegalArgumentException("users must not be null");
    }

    List<String> result = new ArrayList<>();
    for (User user : users) {
        if (user != null && user.isActive()) {
            result.add(user.getName());
        }
    }
    return result;
}
```

Sau khi đọc implementation cũ và xác nhận hành vi được consumer sử dụng, hợp đồng có thể được mô tả như sau:

1. Tham số `users` không được `null`; nếu `null`, method ném `IllegalArgumentException`.
2. Phần tử `null` bên trong danh sách được bỏ qua.
3. Chỉ user có `isActive() == true` được đưa vào kết quả.
4. Thứ tự kết quả giữ theo thứ tự xuất hiện trong danh sách đầu vào.
5. Nếu có tên trùng nhau, các phần tử trùng vẫn được giữ.
6. Kết quả là một `ArrayList` có thể sửa độc lập; sửa kết quả không sửa danh sách đầu vào.
7. Nếu `getName()` trả `null`, giá trị đó vẫn được giữ trong kết quả.

Một bản viết lại bằng Stream API có thể ngắn hơn nhưng làm thay đổi nhiều semantics:

```java
public List<String> findActiveNames(List<User> users) {
    return users.stream()
            .filter(User::isActive)
            .map(User::getName)
            .distinct()
            .toList();
}
```

Bản mới có thể gây ra các khác biệt sau:

- Khi `users == null`, nó ném `NullPointerException` thay vì `IllegalArgumentException`.
- Nếu danh sách chứa phần tử `null`, `User::isActive` gây `NullPointerException` thay vì bỏ qua phần tử đó.
- `distinct()` loại bỏ tên trùng, làm thay đổi số lượng và nội dung kết quả.
- `toList()` trả về danh sách không thể sửa, khác với `ArrayList` có thể sửa của implementation cũ.

Nếu các hành vi trên thuộc hợp đồng cần duy trì, có thể dùng Stream API mà vẫn giữ semantics:

```java
public List<String> findActiveNames(List<User> users) {
    if (users == null) {
        throw new IllegalArgumentException("users must not be null");
    }

    return users.stream()
            .filter(Objects::nonNull)
            .filter(User::isActive)
            .map(User::getName)
            .collect(Collectors.toCollection(ArrayList::new));
}
```

Với đầu vào là `List`, stream giữ encounter order của danh sách. Không dùng `distinct()` nên các tên trùng vẫn còn; `Collectors.toCollection(ArrayList::new)` tạo kết quả có thể sửa; `map(User::getName)` vẫn giữ giá trị `null` nếu tên của user là `null`. Phần kiểm tra đầu vào giữ nguyên loại exception và thông điệp đã cam kết.

Ví dụ này cho thấy thay đổi kỹ thuật chỉ an toàn khi semantics tại ranh giới vẫn được giữ. Việc dùng Stream API tự nó không tạo ra hay phá vỡ tương thích; cách lựa chọn các operation và collector mới là điều quyết định.

### 3.1. Ví dụ khác: giữ quy tắc tính toán tiền tệ

Giả sử hợp đồng tính phí quy định dùng hai chữ số thập phân và làm tròn theo `HALF_UP`:

```java
public BigDecimal calculateFee(BigDecimal amount, BigDecimal rate) {
    return amount.multiply(rate)
            .setScale(2, RoundingMode.HALF_UP);
}
```

Một bản migration đổi sang `double`, hoặc đổi `HALF_UP` thành `HALF_EVEN`, có thể tạo kết quả khác ở các giá trị biên. Khác biệt có thể hiếm gặp trong dữ liệu thông thường nhưng vẫn ảnh hưởng đến hóa đơn, đối soát hoặc báo cáo. Để giữ tương thích, cần duy trì độ chính xác, scale, quy tắc làm tròn, cách xử lý giá trị âm và cách xử lý đầu vào `null` theo hợp đồng hiện có.

## 4. Xác định điều gì cần giữ và điều gì được phép thay đổi

Không nên suy ra toàn bộ hợp đồng chỉ từ implementation. Cần đối chiếu tài liệu API, test hiện có, consumer thực tế, dữ liệu lịch sử và các cam kết vận hành. Có thể chia hành vi thành bốn nhóm:

| Nhóm | Ý nghĩa | Cách xử lý khi migration |
|---|---|---|
| Hợp đồng được công bố | Được ghi trong tài liệu, schema, API hoặc cam kết chính thức | Mặc định phải giữ; nếu thay đổi cần versioning hoặc lộ trình chuyển đổi |
| Hành vi được consumer dựa vào | Không ghi rõ nhưng có bằng chứng consumer đang sử dụng | Xác minh phạm vi ảnh hưởng rồi quyết định giữ, chuyển tiếp hoặc thay đổi có kiểm soát |
| Chi tiết triển khai | Cách làm nội bộ không được phơi ra ngoài | Có thể thay đổi nếu không làm lộ khác biệt qua ranh giới |
| Hành vi lỗi hoặc ngoài hợp đồng | Kết quả bất thường, không được cam kết và không có consumer hợp lệ nên phụ thuộc | Không tự động biến thành hợp đồng; cần đánh giá trước khi sửa hoặc loại bỏ |

Điểm khó thường nằm giữa “hành vi tình cờ” và “hành vi mà consumer đã phụ thuộc”. Chẳng hạn, tài liệu không hứa thứ tự trả về nhưng một consumer đã dựa vào thứ tự đó trong nhiều năm. Việc phụ thuộc này không tự động biến thứ tự thành hợp đồng chính thức, nhưng nó là bằng chứng rủi ro migration. Cần xác định consumer nào bị ảnh hưởng và liệu có thể cập nhật consumer cùng lúc hay không.

Một cách hữu ích là ghi rõ mức cam kết cho từng hành vi:

- **Guaranteed:** được tài liệu hoặc schema cam kết; phải giữ trong phạm vi tương thích đã công bố.
- **Observed and relied upon:** đang được consumer sử dụng; phải đánh giá trước khi thay đổi.
- **Unspecified:** chưa có cam kết và chưa thấy consumer phụ thuộc; không nên dựa vào khi thiết kế tính năng mới.
- **Deprecated:** vẫn được hỗ trợ trong giai đoạn chuyển tiếp nhưng đã có hướng thay thế và mốc loại bỏ.

Việc phân loại giúp tránh hai cực đoan: vô tình phá vỡ hành vi quan trọng, hoặc đóng băng mọi chi tiết cũ kể cả lỗi không còn cần duy trì.

## 5. Quy trình giữ tương thích trong một cuộc migration

### Bước 1: Xác định ranh giới và consumer

Liệt kê các thành phần gọi API, đọc dữ liệu hoặc nhận side effect từ thành phần đang được thay thế. Với Java application, ranh giới có thể là public method, interface giữa module, event listener, repository, file format hoặc REST endpoint. Với thư viện dùng chung, cần xét cả consumer được biên dịch cùng lúc và consumer đã được biên dịch từ phiên bản cũ.

Đừng chỉ tìm nơi gọi trực tiếp. Hành vi có thể được truyền qua adapter, callback, message broker, cache hoặc một tiến trình khác. Một API nội bộ trong cùng repository vẫn có thể là hợp đồng thực tế nếu nhiều module phụ thuộc vào nó.

### Bước 2: Mô tả hợp đồng theo tình huống

Với mỗi thao tác, ghi các trường hợp thành công, đầu vào biên, trạng thái trước và sau, side effect, lỗi và thứ tự. Tập trung vào câu hỏi mà consumer có thể quan sát. Nếu một chi tiết chưa rõ, đánh dấu chưa xác định thay vì tự giả định.

Ví dụ, với `transfer(source, target, amount)`, hợp đồng nên làm rõ: số tiền bằng không có hợp lệ không; tài khoản không tồn tại gây lỗi gì; chuyển khoản thất bại có được ghi một phần không; hai tài khoản có được cập nhật nguyên tử không; request gửi lại có tạo giao dịch lần hai không; và sự kiện được phát trước hay sau commit.

### Bước 3: Ghi nhận baseline của phiên bản cũ

Khi tài liệu thiếu, characterization test giúp ghi lại hành vi đang chạy. Test nên dùng đầu vào đại diện, bao gồm giá trị biên và trường hợp lỗi. Với hệ thống có side effect, cần quan sát cả trạng thái lưu trữ, message phát ra và số lần gọi dịch vụ ngoài.

Characterization test ghi nhận điều implementation cũ thực sự làm; nó chưa khẳng định hành vi đó là thiết kế đúng. Sau khi có baseline, nhóm phát triển phải phân loại hành vi nào là hợp đồng, hành vi nào là phụ thuộc ngoài dự kiến và hành vi nào là bug cần sửa có chủ đích.

### Bước 4: Chạy cùng tình huống trên implementation mới

Dùng cùng bộ dữ liệu và kịch bản để so sánh phiên bản cũ với phiên bản mới. So sánh cấu trúc và ý nghĩa dữ liệu, không chỉ so sánh chuỗi log. Với API, so sánh status, header, body và semantics lỗi. Với thao tác ghi dữ liệu, so sánh trạng thái cuối và hiệu ứng phụ. Với xử lý đồng thời, cần có kịch bản kiểm tra interleaving và tính nguyên tử phù hợp.

### Bước 5: Dùng adapter hoặc lớp tương thích khi cần

Nếu thư viện mới có semantics khác, đặt adapter tại ranh giới để chuyển đổi về hợp đồng mà consumer cũ đang sử dụng. Adapter có thể chuẩn hóa exception, chuyển `Optional` thành kiểu kết quả cũ, khôi phục thứ tự, chuyển enum mới sang giá trị legacy hoặc ánh xạ schema dữ liệu.

Ví dụ, nếu thư viện mới ném `NewClientException` nhưng API của ứng dụng đã cam kết `RemoteServiceException`, adapter có thể bắt exception mới và ánh xạ sang exception công khai cũ. Consumer tiếp tục nhìn thấy hợp đồng quen thuộc trong khi phần triển khai bên trong được thay thế.

Adapter nên có phạm vi rõ ràng và được kiểm thử như một ranh giới hợp đồng. Nếu giữ adapter vô thời hạn, cần ghi nhận trách nhiệm bảo trì; nếu chỉ dùng cho giai đoạn chuyển tiếp, cần xác định điều kiện và thời điểm loại bỏ.

### Bước 6: Triển khai theo giai đoạn và theo dõi

Với hệ thống lớn, có thể dùng expand-and-contract: mở rộng schema hoặc API để cả phiên bản cũ và mới cùng hoạt động; chuyển consumer từng bước; xác nhận không còn traffic phụ thuộc hành vi cũ; sau đó mới loại bỏ phần legacy. Với dữ liệu, có thể cần dual-read hoặc dual-write có kiểm soát, nhưng phải định nghĩa nguồn dữ liệu chuẩn và cách xử lý sai lệch.

Theo dõi production nên tập trung vào tín hiệu có ý nghĩa đối với hợp đồng: tỷ lệ lỗi theo loại, số bản ghi được tạo, số message phát, độ trễ theo SLO, số lần retry và chênh lệch kết quả. Log thành công chung chung không đủ để chứng minh hai phiên bản tương thích.

### Bước 7: Công bố thay đổi khi không thể giữ hợp đồng

Đôi khi semantics cũ không còn phù hợp hoặc không thể duy trì an toàn. Khi đó, cần xem đây là thay đổi hợp đồng: xác định consumer chịu ảnh hưởng, cung cấp phiên bản hoặc endpoint mới nếu cần, công bố ví dụ trước/sau, thời gian deprecation, hướng chuyển đổi và cách xác nhận consumer đã di chuyển.

Không nên âm thầm thay đổi hành vi rồi trông đợi consumer tự phát hiện. Một thay đổi breaking có chủ đích vẫn có thể là quyết định kỹ thuật tốt nếu được quản lý như một migration thực sự.

## 6. Kiểm thử tương thích hành vi

Các lớp kiểm thử khác nhau phát hiện những rủi ro khác nhau. Một bộ kiểm thử hữu ích thường kết hợp:

1. **Unit test:** xác minh quy tắc đầu vào, đầu ra, lỗi và bất biến ở phạm vi nhỏ.
2. **Contract test:** xác minh producer và consumer thống nhất về schema, semantics và giao thức tại ranh giới.
3. **Characterization test:** ghi nhận hành vi phiên bản cũ khi tài liệu không mô tả đủ.
4. **Differential test:** chạy cùng input qua hai implementation và so sánh kết quả hoặc side effect.
5. **Integration test:** xác minh transaction, persistence, message, cache và các thành phần thực tế phối hợp đúng.
6. **Compatibility test với consumer cũ:** xác minh bytecode, cấu hình hoặc payload do consumer cũ tạo ra vẫn được phiên bản mới xử lý khi đó là cam kết hỗ trợ.

Một ví dụ JUnit 5 cho hợp đồng của phương thức ở phần trước:

```java
@Test
void preservesOrderDuplicatesAndMutableResult() {
    List<User> input = List.of(
            activeUser("An"),
            activeUser("Binh"),
            activeUser("An"),
            inactiveUser("Chi")
    );

    List<String> result = service.findActiveNames(input);

    assertEquals(List.of("An", "Binh", "An"), result);
    assertDoesNotThrow(() -> result.add("Dung"));
    assertEquals(4, input.size());
}

@Test
void rejectsNullListWithTheContractedException() {
    assertThrows(
            IllegalArgumentException.class,
            () -> service.findActiveNames(null)
    );
}
```

Test đầu tiên kiểm tra thứ tự, phần tử trùng và khả năng sửa kết quả. Test thứ hai kiểm tra loại exception của đầu vào không hợp lệ. Trong dự án thật, nên bổ sung trường hợp phần tử `null`, tên `null`, danh sách rỗng và xác minh việc sửa kết quả không tác động ngược lên dữ liệu đầu vào nếu đó là cam kết.

Không nên viết test khóa chặt chi tiết nội bộ như tên biến, số vòng lặp, thứ tự gọi private method hoặc loại collection nội bộ nếu consumer không quan sát được. Những test như vậy làm migration khó hơn nhưng không chứng minh được tương thích hành vi.

### 6.1. Kiểm thử cả lỗi và side effect

Một test chỉ xác nhận method ném exception chưa chắc đã đủ. Với thao tác cập nhật dữ liệu, cần kiểm tra trạng thái sau lỗi để xác nhận transaction rollback đúng. Với thao tác phát event, cần kiểm tra event được phát đúng số lần và đúng thời điểm. Với retry, cần xác minh thao tác có idempotent theo hợp đồng hay không.

Ví dụ, nếu `confirmOrder()` được cam kết chỉ phát `OrderConfirmed` sau khi transaction commit, test cần quan sát cả trạng thái đơn hàng và event. Nếu event bị phát trước commit rồi transaction rollback, consumer nhận được một thông báo sai dù method cuối cùng trả lỗi.

### 6.2. Dữ liệu biên thường phát hiện khác biệt

Nên chủ động kiểm tra các giá trị mà implementation mới dễ xử lý khác implementation cũ:

- `null`, chuỗi rỗng, collection rỗng và phần tử `null`;
- số âm, số không, giá trị rất lớn, số thập phân ở đúng điểm làm tròn;
- ký tự Unicode, timezone, locale và định dạng ngày giờ;
- dữ liệu trùng, dữ liệu không theo thứ tự và dữ liệu thiếu trường;
- timeout, retry, request gửi lặp và hai thao tác chạy đồng thời;
- enum hoặc schema có thêm giá trị mà consumer cũ chưa biết.

Các tình huống này đặc biệt quan trọng khi đổi thư viện, đổi JDK, chuyển database, thay serializer hoặc thay cách xử lý bất đồng bộ.

## 7. Những nguồn thay đổi hành vi thường gặp trong Java

### 7.1. Collection và Stream API

Đổi `List` sang `Set` có thể làm mất phần tử trùng và thay đổi thứ tự. Đổi `ArrayList` sang `List.of(...)` hoặc `Stream.toList()` có thể làm collection trở thành immutable. Dùng `HashMap` hoặc `HashSet` có thể khiến code dựa vào thứ tự tình cờ ngừng hoạt động. Dùng `parallelStream()` có thể thay đổi thứ tự thực thi và làm lộ race condition nếu lambda có side effect.

Khi migration, cần kiểm tra encounter order, duplicate handling, mutability, null policy và thread-safety. Nếu thứ tự không phải hợp đồng, consumer cũng không nên dựa vào nó; nếu thứ tự quan trọng, hãy biểu diễn rõ bằng kiểu dữ liệu và comparator phù hợp.

### 7.2. Exception và cách biểu diễn kết quả thiếu

Đổi từ exception sang `Optional`, từ `null` sang empty object, hoặc đổi checked exception sang unchecked exception đều có thể làm thay đổi cách consumer xử lý thất bại. Cần phân biệt “không tìm thấy”, “đầu vào sai”, “không có quyền”, “dịch vụ tạm thời không sẵn sàng” và “lỗi hệ thống”. Gộp các trường hợp này thành một giá trị mặc định thường làm mất thông tin mà consumer cần để retry hoặc phản hồi chính xác.

### 7.3. Date/time, locale và timezone

Đổi từ `Date`/`Calendar` sang `java.time` có thể là cải tiến tốt, nhưng phải xác định semantics của thời điểm và múi giờ. `LocalDateTime` không đại diện cho một instant duy nhất nếu thiếu timezone. Định dạng ngày theo default locale hoặc timezone của máy có thể khiến cùng một dữ liệu tạo ra output khác giữa môi trường phát triển và production. Hãy truyền `ZoneId`, `Locale` hoặc `Clock` tường minh khi chúng thuộc hợp đồng.

### 7.4. Serialization và cấu hình

Thay Jackson version, naming strategy hoặc cấu hình enum có thể đổi JSON output và cách deserialize. Giá trị `null` có thể bị bỏ qua thay vì xuất hiện; field mới có thể có default khác; enum không nhận diện có thể gây lỗi hoặc được ánh xạ về giá trị mặc định. Khi dữ liệu được lưu lâu dài hoặc trao đổi với consumer độc lập, schema và quy tắc tương thích cần được kiểm tra như một phần của hợp đồng hành vi.

### 7.5. Transaction và xử lý bất đồng bộ

Chuyển một thao tác đồng bộ sang `@Async`, message queue hoặc reactive pipeline có thể thay đổi thời điểm lỗi được báo, thứ tự xử lý và thời điểm dữ liệu trở nên nhìn thấy. Consumer trước đây nhận exception trực tiếp có thể nay chỉ nhận được lỗi qua callback hoặc dead-letter queue. Cần mô tả rõ delivery semantics, retry, ordering, idempotency và ranh giới transaction.

## 8. Các lỗi tư duy thường gặp

- **Chỉ kiểm tra biên dịch:** code compile được không chứng minh kết quả runtime còn tương thích.
- **Chỉ kiểm tra chữ ký API:** giữ tên method và kiểu trả về không đảm bảo giữ semantics.
- **Chỉ so sánh happy path:** khác biệt thường xuất hiện ở đầu vào biên, lỗi, retry và trạng thái một phần.
- **Xem mọi hành vi quan sát được là hợp đồng:** điều này có thể đóng băng bug hoặc chi tiết nội bộ. Cần phân loại bằng tài liệu và bằng chứng consumer.
- **Xem hành vi không được tài liệu hóa là không quan trọng:** consumer thực tế có thể đã phụ thuộc vào nó. Cần tìm và đánh giá consumer trước khi thay đổi.
- **Dùng adapter nhưng không có kế hoạch loại bỏ:** lớp chuyển tiếp có thể trở thành nợ kỹ thuật nếu không có owner và điều kiện kết thúc.
- **So sánh log thay cho trạng thái:** log giống nhau không chứng minh database, message hoặc side effect giống nhau.
- **Thay đổi nhiều semantics cùng lúc:** khi kết quả khác, rất khó xác định thay đổi nào gây ra regression. Nên chia migration thành các bước có thể quan sát và kiểm chứng.

## 9. Checklist trước khi kết luận migration giữ tương thích hành vi

- [ ] Đã xác định consumer và ranh giới giao tiếp chịu ảnh hưởng.
- [ ] Đã mô tả đầu vào hợp lệ, đầu ra, lỗi và trạng thái sau thao tác.
- [ ] Đã kiểm tra thứ tự, duplicate, mutability và null policy khi có liên quan.
- [ ] Đã ghi nhận side effect, transaction, retry và idempotency.
- [ ] Đã phân biệt hợp đồng được công bố, hành vi consumer đang dựa vào và chi tiết triển khai.
- [ ] Đã có baseline hoặc contract test cho các hành vi quan trọng.
- [ ] Đã so sánh implementation mới trên cùng bộ tình huống, gồm cả trường hợp lỗi và dữ liệu biên.
- [ ] Adapter hoặc cơ chế chuyển tiếp có phạm vi, owner và điều kiện loại bỏ rõ ràng.
- [ ] Breaking change được công bố với consumer bị ảnh hưởng và hướng migration cụ thể.
- [ ] Tín hiệu production theo dõi được các kết quả và side effect quan trọng của hợp đồng.

## 10. Kết luận

Tương thích hành vi là khả năng duy trì những cam kết mà consumer có thể quan sát khi implementation thay đổi. Muốn giữ được nó, cần mô tả hợp đồng ở ranh giới, nhận diện consumer, ghi nhận baseline, kiểm thử cả thành công lẫn thất bại và quản lý các thay đổi semantics theo lộ trình rõ ràng. Một migration tốt có thể thay đổi sâu cách hệ thống được xây dựng, miễn là những hành vi đã cam kết tiếp tục đúng; nếu cần thay đổi hợp đồng, sự thay đổi đó phải được nhận diện và truyền đạt như một phần chính thức của migration.
