# Kiểu phản hồi tổng quát và ParameterizedTypeReference

## 1. Vấn đề: Java generic bị type erasure

Khi gọi RSocket bằng Spring, phía client thường biết kiểu dữ liệu mong muốn nhận về. Với kiểu đơn giản như String, User hoặc Order, ta có thể truyền trực tiếp Class:

~~~java
Mono<User> user = requester
    .route("users.find")
    .data(userId)
    .retrieveMono(User.class);
~~~

Khó khăn xuất hiện khi kiểu phản hồi có tham số generic, chẳng hạn List<User>, ApiResponse<User> hoặc ApiResponse<List<Order>>. Java xóa phần lớn thông tin tham số generic ở runtime (type erasure). Vì vậy, List<User>.class không phải cú pháp Java hợp lệ; List.class chỉ biểu diễn kiểu raw List và không nói được phần tử bên trong là User.

Nếu chỉ cung cấp List.class, bộ chuyển đổi dữ liệu ở phía nhận có thể chỉ biết kết quả là một danh sách mà không có đủ thông tin kiểu để chuyển từng phần tử thành User. Tùy codec và dữ liệu, phần tử có thể trở thành Map hoặc kiểu trung gian khác. Vấn đề tương tự xảy ra với các lớp bao generic như ApiResponse<T>: chỉ truyền ApiResponse.class không thể hiện T là User hay List<Order>.

## 2. ParameterizedTypeReference là gì?

org.springframework.core.ParameterizedTypeReference<T> là lớp tiện ích của Spring dùng để giữ lại thông tin kiểu generic đầy đủ dưới dạng java.lang.reflect.Type. Nó khai thác generic superclass của một lớp con ẩn danh để chụp lại tham số kiểu tại thời điểm tạo đối tượng.

Mẫu sử dụng phổ biến:

~~~java
ParameterizedTypeReference<List<User>> userListType =
    new ParameterizedTypeReference<List<User>>() {};

Mono<List<User>> users = requester
    .route("users.all")
    .retrieveMono(userListType);
~~~

Cặp ngoặc nhọn cuối cùng tạo một lớp con ẩn danh. Thông tin List<User> được khai báo trên lớp con đó, nên Spring có thể đọc được Type đã tham số hóa qua reflection. Nếu chỉ tạo ParameterizedTypeReference<List<User>>() mà không có phần thân lớp con ẩn danh, Java không cho phép khởi tạo trực tiếp lớp abstract này.

Có thể viết ngắn ngay tại nơi gọi:

~~~java
Mono<List<User>> users = requester
    .route("users.all")
    .retrieveMono(new ParameterizedTypeReference<List<User>>() {});
~~~

Đối tượng tham chiếu kiểu chỉ mô tả kiểu đích. Nó không tự thực hiện chuyển đổi dữ liệu và cũng không thay thế codec. Việc giải mã payload vẫn do các codec được cấu hình trong RSocket/Spring đảm nhiệm; codec phải hỗ trợ kiểu dữ liệu và định dạng payload đang dùng.

## 3. Dùng với RSocketRequester

RSocketRequester cung cấp API fluent để tạo request. Sau khi khai báo route và dữ liệu gửi đi, retrieveMono hoặc retrieveFlux xác định kiểu phản hồi mong muốn. Với kiểu generic, dùng overload nhận ParameterizedTypeReference.

~~~java
Mono<ApiResponse<List<User>>> response = requester
    .route("users.search")
    .data(criteria)
    .retrieveMono(
        new ParameterizedTypeReference<ApiResponse<List<User>>>() {}
    );
~~~

Trong ví dụ này, kiểu đích là toàn bộ cấu trúc ApiResponse<List<User>>. Thông tin generic được giữ ở cả hai tầng: ApiResponse chứa List và List chứa User. Chỉ truyền ApiResponse.class hoặc List.class sẽ làm mất phần thông tin tham số cần thiết.

Nếu endpoint trả về một luồng nhiều phần tử, retrieveFlux cũng có overload nhận ParameterizedTypeReference:

~~~java
Flux<ApiResponse<User>> events = requester
    .route("users.events")
    .retrieveFlux(
        new ParameterizedTypeReference<ApiResponse<User>>() {}
    );
~~~

Hãy chọn Mono hay Flux theo hợp đồng phản hồi của route: Mono biểu diễn tối đa một kết quả, còn Flux biểu diễn một chuỗi phần tử. ParameterizedTypeReference xác định kiểu của mỗi kết quả, không quyết định cardinality hay mô hình tương tác RSocket.

## 4. Ví dụ đầy đủ về kiểu generic lồng nhau

Ví dụ sau minh họa DTO generic và cách gọi. Đây là đoạn mã minh họa API; các kiểu User, SearchCriteria và route users.search cần được định nghĩa/phía server hỗ trợ trong ứng dụng thực tế.

~~~java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.core.publisher.Mono;

import java.util.List;

record User(Long id, String name) {}

record ApiResponse<T>(
    boolean success,
    T data,
    String message
) {}

record SearchCriteria(String keyword) {}

class UserClient {
    private final RSocketRequester requester;

    UserClient(RSocketRequester requester) {
        this.requester = requester;
    }

    Mono<ApiResponse<List<User>>> search(String keyword) {
        SearchCriteria criteria = new SearchCriteria(keyword);

        return requester
            .route("users.search")
            .data(criteria)
            .retrieveMono(
                new ParameterizedTypeReference<ApiResponse<List<User>>>() {}
            );
    }
}
~~~

Kiểu trả về của phương thức là Mono<ApiResponse<List<User>>>. Kiểu generic truyền cho retrieveMono phải khớp với cấu trúc payload mà server gửi. Nếu server thực tế trả ApiResponse<User> hoặc List<User> trực tiếp, hãy khai báo đúng kiểu đó thay vì ép kiểu theo mong muốn của client.

## 5. So sánh Class<T> và ParameterizedTypeReference<T>

| Nhu cầu | Cách truyền kiểu | Ví dụ |
|---|---|---|
| Kiểu cụ thể, không có generic | Class<T> | User.class |
| String hoặc kiểu đơn giản | Class<T> | String.class |
| Danh sách có kiểu phần tử | ParameterizedTypeReference<T> | new ParameterizedTypeReference<List<User>>() {} |
| DTO bao một kiểu generic | ParameterizedTypeReference<T> | ApiResponse<User> |
| Generic lồng nhau | ParameterizedTypeReference<T> | ApiResponse<List<User>> |

Quy tắc thực hành: dùng Class<T> khi kiểu đích được biểu diễn đầy đủ bằng một Class. Dùng ParameterizedTypeReference<T> khi cần giữ tham số generic ở runtime.

## 6. Vì sao không thể dùng List.class rồi ép kiểu?

Đoạn sau biên dịch được nhưng không bảo đảm các phần tử đã được giải mã thành User:

~~~java
Mono<List> raw = requester
    .route("users.all")
    .retrieveMono(List.class);

Mono<List<User>> users = raw.cast(List.class);
~~~

Cast ở đây chỉ kiểm tra/cast đối tượng List bên ngoài. Nó không biến từng phần tử thành User và không khôi phục thông tin generic đã mất. Ép kiểu unchecked có thể che giấu lỗi cho tới khi ứng dụng truy cập phần tử và gặp ClassCastException hoặc lỗi xử lý dữ liệu.

Hãy khai báo kiểu đích đầy đủ ngay tại ranh giới giải mã:

~~~java
Mono<List<User>> users = requester
    .route("users.all")
    .retrieveMono(new ParameterizedTypeReference<List<User>>() {});
~~~

Điều này giúp codec có đủ thông tin kiểu để chuyển đổi payload, đồng thời giúp compiler kiểm tra kiểu ở phần còn lại của chương trình.

## 7. Tái sử dụng tham chiếu kiểu

Nếu một kiểu generic được dùng ở nhiều nơi, có thể khai báo hằng số để tránh lặp lại anonymous subclass:

~~~java
private static final ParameterizedTypeReference<ApiResponse<List<User>>>
    USER_LIST_RESPONSE_TYPE =
        new ParameterizedTypeReference<ApiResponse<List<User>>>() {};

Mono<ApiResponse<List<User>>> search(SearchCriteria criteria) {
    return requester
        .route("users.search")
        .data(criteria)
        .retrieveMono(USER_LIST_RESPONSE_TYPE);
}
~~~

Hằng số này an toàn để tái sử dụng vì ParameterizedTypeReference chỉ giữ thông tin kiểu, không chứa trạng thái của request. Mỗi request vẫn được tạo riêng qua RSocketRequester.

## 8. Lỗi thường gặp và cách kiểm tra

- **Dùng List.class cho List<User>:** kiểu phần tử bị mất. Thay bằng ParameterizedTypeReference<List<User>>.
- **Chỉ khai báo lớp bao:** ApiResponse.class không thể hiện ApiResponse<User>. Truyền đầy đủ ApiResponse<User>.
- **Quên lớp con ẩn danh:** dùng đúng cú pháp new ParameterizedTypeReference<T>() {} để chụp generic type.
- **Ép kiểu sau khi nhận dữ liệu:** cast không giải mã lại payload. Sửa kiểu đích ở retrieveMono/retrieveFlux.
- **Kiểu client không khớp payload server:** kiểm tra hợp đồng route, DTO, cấu trúc JSON/CBOR và codec hai phía.
- **Cho rằng ParameterizedTypeReference tự chuyển đổi dữ liệu:** nó chỉ cung cấp metadata kiểu; codec mới thực hiện encode/decode.
- **Chọn sai Mono/Flux:** kiểm tra mô hình phản hồi của route. Kiểu generic và số lượng phần tử là hai quyết định riêng.

Khi debug, kiểm tra kiểu generic đã truyền vào retrieveMono/retrieveFlux, cấu trúc payload thực tế và codec được cấu hình. Có thể viết integration test với RSocket server/client thật để xác nhận cả kiểu phần tử sau giải mã, đặc biệt với DTO generic lồng nhau. Không nên chỉ kiểm tra đối tượng ngoài cùng là List hoặc ApiResponse.

## 9. Ghi nhớ

ParameterizedTypeReference giải quyết khoảng trống do type erasure khi Spring cần biết một kiểu generic đầy đủ ở runtime. Với RSocketRequester, truyền tham chiếu này vào retrieveMono hoặc retrieveFlux để mô tả chính xác kiểu phản hồi như List<User> hay ApiResponse<List<User>>. Nó cung cấp thông tin kiểu cho quá trình giải mã; codec và hợp đồng payload giữa client/server vẫn phải tương thích.
