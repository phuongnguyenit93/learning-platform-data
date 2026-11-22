# Kiểm thử metadata bắt buộc và tùy chọn

Trong một API Spring gRPC, metadata có thể mang thông tin mà server cần để xử lý một lời gọi, chẳng hạn request ID, tenant selection hoặc locale. Một số key là **bắt buộc theo hợp đồng ứng dụng**; một số key **tùy chọn** và có quy tắc mặc định khi vắng mặt. Kiểm thử phải xác minh cả hai trường hợp, đồng thời phân biệt metadata bị thiếu với metadata có mặt nhưng sai định dạng.

gRPC không tự định nghĩa mọi custom key là bắt buộc hay tùy chọn. Đây là quyết định của API. Bài này xây dựng một hợp đồng mẫu cho RPC `GetOrder`: `x-request-id` bắt buộc để truy vết, `x-locale` tùy chọn với mặc định `vi-VN`. Sau đó kiểm tra validation, status, interceptor và đường truyền thực qua in-process gRPC.

## 1. Viết rõ hợp đồng trước khi viết test

Một metadata contract cần nói rõ key nào được chấp nhận, ai cung cấp, kiểu dữ liệu, số lượng value, định dạng, giới hạn và cách xử lý khi vắng mặt.

| Key | Phân loại | Quy tắc mẫu | Khi không hợp lệ |
| --- | --- | --- | --- |
| `x-request-id` | Bắt buộc | Một value ASCII, 1–64 ký tự `[A-Za-z0-9._-]` | `INVALID_ARGUMENT` |
| `x-locale` | Tùy chọn | Một value ASCII thuộc `vi-VN` hoặc `en-US` | `INVALID_ARGUMENT` |
| `authorization` | Bắt buộc theo bảo mật | Credentials được xác minh bằng authentication layer | `UNAUTHENTICATED` nếu thiếu/sai |
| Key không biết | Không được API sử dụng | Bỏ qua nếu không ảnh hưởng policy; không đưa vào logic nghiệp vụ | Theo chính sách API/gateway |

Trong ví dụ, nếu `x-locale` **vắng mặt**, server chọn `vi-VN`. Nếu key có mặt nhưng value rỗng hoặc không hỗ trợ, server trả `INVALID_ARGUMENT`. Quy tắc này tránh việc một client gửi sai dữ liệu mà server âm thầm xem như không gửi.

### Bắt buộc và tùy chọn không đồng nghĩa với có/không có trong mọi request

- **Bắt buộc:** client phải gửi key trong mọi call thuộc phạm vi API; server từ chối nếu thiếu hoặc không hợp lệ.
- **Tùy chọn:** client có thể bỏ key; server áp dụng default đã công bố.
- **Tùy chọn nhưng có mặt:** nếu gửi thì value vẫn phải hợp lệ. Optional không có nghĩa là chấp nhận chuỗi rỗng hoặc dữ liệu sai.
- **Không biết:** key mới hoặc không được service sử dụng không nên tự động làm hỏng client cũ, trừ khi security policy yêu cầu chặn.

Không dùng request ID làm credential. Nếu `authorization` bắt buộc, kiểm tra nó bằng cơ chế xác thực riêng và giữ đúng status `UNAUTHENTICATED`; không gộp lỗi credentials vào lỗi định dạng metadata nghiệp vụ.

## 2. Ma trận kiểm thử cần có

Kiểm thử chỉ một request thành công không chứng minh được contract. Với mỗi key, cần kiểm tra sự hiện diện, số lượng value và nội dung.

| Trường hợp | `x-request-id` | `x-locale` | Kết quả mong đợi |
| --- | --- | --- | --- |
| Đủ metadata tối thiểu | Hợp lệ | Vắng mặt | Thành công; locale mặc định `vi-VN` |
| Đủ metadata tường minh | Hợp lệ | `en-US` | Thành công; locale `en-US` |
| Thiếu key bắt buộc | Vắng mặt | Vắng mặt | `INVALID_ARGUMENT` |
| Required value rỗng | Chuỗi rỗng | Vắng mặt | `INVALID_ARGUMENT` |
| Required value sai định dạng | Có dấu cách/newline hoặc quá dài | Vắng mặt | `INVALID_ARGUMENT` |
| Optional value rỗng | Hợp lệ | Chuỗi rỗng | `INVALID_ARGUMENT` theo contract mẫu |
| Optional value không hỗ trợ | Hợp lệ | `fr-FR` | `INVALID_ARGUMENT` theo contract mẫu |
| Key bắt buộc bị lặp | Hai value | Vắng mặt | `INVALID_ARGUMENT` |
| Key tùy chọn bị lặp | Hợp lệ | Hai value | `INVALID_ARGUMENT` |
| Credentials thiếu/sai | Hợp lệ | Bất kỳ | `UNAUTHENTICATED` ở authentication layer |

Ngoài ma trận giá trị, kiểm thử cần xác minh:

- Service không được gọi khi validation thất bại.
- Metadata đã kiểm tra được chuyển vào đúng `io.grpc.Context`.
- Hai RPC đồng thời không dùng nhầm context của nhau.
- Client gửi qua proxy/transport thực tế vẫn giữ key theo contract.
- Lỗi không làm lộ token hoặc toàn bộ metadata trong log.

## 3. Viết validator tách biệt để dễ kiểm thử

Tách quy tắc metadata khỏi interceptor giúp unit test không cần khởi động server. `Metadata.getAll(...)` được dùng để phát hiện key lặp; `get(...)` một mình chỉ trả value cuối cùng và có thể che giấu duplicate.

```java
import io.grpc.Metadata;

final class OrderRequestMetadata {
    static final Metadata.Key<String> REQUEST_ID =
        Metadata.Key.of(
            "x-request-id", Metadata.ASCII_STRING_MARSHALLER);
    static final Metadata.Key<String> LOCALE =
        Metadata.Key.of(
            "x-locale", Metadata.ASCII_STRING_MARSHALLER);

    final String requestId;
    final String locale;

    private OrderRequestMetadata(String requestId, String locale) {
        this.requestId = requestId;
        this.locale = locale;
    }

    static OrderRequestMetadata parse(Metadata headers) {
        String requestId = single(headers, REQUEST_ID);
        String locale = single(headers, LOCALE);

        if (requestId == null
                || !requestId.matches("[A-Za-z0-9._-]{1,64}")) {
            throw new IllegalArgumentException("Invalid x-request-id");
        }

        if (locale == null) {
            locale = "vi-VN";
        } else if (!locale.equals("vi-VN") && !locale.equals("en-US")) {
            throw new IllegalArgumentException("Unsupported x-locale");
        }

        return new OrderRequestMetadata(requestId, locale);
    }

    private static String single(
            Metadata headers, Metadata.Key<String> key) {
        Iterable<String> values = headers.getAll(key);
        if (values == null) {
            return null;
        }
        java.util.Iterator<String> iterator = values.iterator();
        if (!iterator.hasNext()) {
            return null;
        }
        String value = iterator.next();
        if (iterator.hasNext()) {
            throw new IllegalArgumentException("Repeated metadata key");
        }
        return value;
    }
}
```

`parse(...)` thể hiện chính sách của ví dụ: request ID bắt buộc, locale tùy chọn, value rỗng không được chấp nhận và key chỉ được xuất hiện một lần. Trong API thật, có thể dùng BCP 47 parser và danh sách locale hỗ trợ rộng hơn; điều quan trọng là contract và test phải thống nhất.

## 4. Gắn validator vào ServerInterceptor

Interceptor chuyển lỗi validation thành gRPC status trước khi gọi service. Chỉ metadata đã qua kiểm tra mới được đưa vào context:

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;

final class RequiredOptionalMetadataInterceptor
        implements ServerInterceptor {

    static final Context.Key<String> REQUEST_ID =
        Context.key("request-id");
    static final Context.Key<String> LOCALE =
        Context.key("request-locale");

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {
        final OrderRequestMetadata parsed;
        try {
            parsed = OrderRequestMetadata.parse(headers);
        } catch (IllegalArgumentException ex) {
            call.close(
                Status.INVALID_ARGUMENT.withDescription(
                    "Invalid request metadata"),
                new Metadata());
            return new ServerCall.Listener<ReqT>() {};
        }

        Context context = Context.current()
            .withValue(REQUEST_ID, parsed.requestId)
            .withValue(LOCALE, parsed.locale);
        return Contexts.interceptCall(context, call, headers, next);
    }
}
```

Mô tả status gửi về client được giữ chung chung; không đưa value metadata vào lỗi. Authentication nên chạy trong interceptor/lớp bảo mật riêng, để thiếu hoặc sai token trả `UNAUTHENTICATED` thay vì `INVALID_ARGUMENT`.

Service có thể đọc context sau khi interceptor cho phép call:

```java
String requestId = RequiredOptionalMetadataInterceptor.REQUEST_ID.get();
String locale = RequiredOptionalMetadataInterceptor.LOCALE.get();

// Dùng requestId cho correlation log đã được kiểm tra.
// Dùng locale cho nội dung được địa phương hóa theo hợp đồng.
```

## 5. Unit test cho required và optional metadata

Unit test xác minh validator theo từng trường hợp. Ví dụ JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;

import io.grpc.Metadata;
import org.junit.jupiter.api.Test;

class OrderRequestMetadataTest {
    @Test
    void requiredKeyMustBePresent() {
        Metadata headers = new Metadata();
        assertThrows(
            IllegalArgumentException.class,
            () -> OrderRequestMetadata.parse(headers));
    }

    @Test
    void optionalLocaleUsesDefaultWhenAbsent() {
        Metadata headers = new Metadata();
        headers.put(OrderRequestMetadata.REQUEST_ID, "req-42");

        OrderRequestMetadata parsed = OrderRequestMetadata.parse(headers);

        assertEquals("req-42", parsed.requestId);
        assertEquals("vi-VN", parsed.locale);
    }

    @Test
    void acceptsSupportedOptionalLocale() {
        Metadata headers = new Metadata();
        headers.put(OrderRequestMetadata.REQUEST_ID, "req-43");
        headers.put(OrderRequestMetadata.LOCALE, "en-US");

        OrderRequestMetadata parsed = OrderRequestMetadata.parse(headers);
        assertEquals("en-US", parsed.locale);
    }

    @Test
    void rejectsEmptyOptionalValueWhenPresent() {
        Metadata headers = new Metadata();
        headers.put(OrderRequestMetadata.REQUEST_ID, "req-44");
        headers.put(OrderRequestMetadata.LOCALE, "");

        assertThrows(
            IllegalArgumentException.class,
            () -> OrderRequestMetadata.parse(headers));
    }

    @Test
    void rejectsRepeatedRequiredKey() {
        Metadata headers = new Metadata();
        headers.put(OrderRequestMetadata.REQUEST_ID, "req-a");
        headers.put(OrderRequestMetadata.REQUEST_ID, "req-b");

        assertThrows(
            IllegalArgumentException.class,
            () -> OrderRequestMetadata.parse(headers));
    }
}
```

Thêm test cho value quá dài, ký tự không hợp lệ, optional locale không hỗ trợ và duplicate optional key. Unit test không chứng minh interceptor đã được đăng ký hoặc service không chạy khi bị từ chối; điều đó cần integration test.

## 6. Integration test qua in-process gRPC

Để xác minh cả đường đi, dựng một server test có interceptor và một generated stub có thể attach metadata. Service test trả lại context đã được interceptor thiết lập:

```java
import io.grpc.stub.StreamObserver;

final class MetadataProbeService extends MetadataProbeGrpc.MetadataProbeImplBase {
    @Override
    public void inspect(
            MetadataProbeRequest request,
            StreamObserver<MetadataProbeReply> observer) {
        String id = RequiredOptionalMetadataInterceptor.REQUEST_ID.get();
        String locale = RequiredOptionalMetadataInterceptor.LOCALE.get();
        observer.onNext(MetadataProbeReply.newBuilder()
            .setRequestId(id)
            .setLocale(locale)
            .build());
        observer.onCompleted();
    }
}
```

Trong test, đăng ký service qua `ServerInterceptors.intercept(...)`, gọi bằng `InProcessChannelBuilder`, rồi tạo stub với `MetadataUtils.newAttachHeadersInterceptor(headers)`. Hai trường hợp thành công cần xác minh:

1. Chỉ gửi `x-request-id`: response có request ID tương ứng và locale mặc định `vi-VN`.
2. Gửi cả `x-request-id` và `x-locale: en-US`: response có locale `en-US`.

Với trường hợp lỗi, gửi request thiếu request ID hoặc locale không hợp lệ; assert `StatusRuntimeException` có code `INVALID_ARGUMENT`. Đồng thời dùng counter trong service test để xác minh method không được gọi khi interceptor từ chối call.

`InProcessServerBuilder` và `InProcessChannelBuilder` kiểm tra logic gRPC/interceptor trong cùng tiến trình. Chúng không mô phỏng đầy đủ TLS, HTTP/2 proxy, gateway header filtering hoặc giới hạn header ở production.

## 7. Kiểm thử tương thích khi contract thay đổi

Metadata contract cũng là một phần của tương thích giữa client và server. Khi thêm key mới:

- **Thêm key tùy chọn:** thường tương thích hơn nếu server cũ bỏ qua key không biết và server mới có default rõ ràng.
- **Thêm key bắt buộc:** có thể làm client cũ bị từ chối ngay khi triển khai server mới. Cần versioning, rollout theo giai đoạn hoặc cơ chế fallback.
- **Đổi tên key:** tương đương thay đổi contract; cân nhắc thời gian hỗ trợ cả tên cũ và mới.
- **Đổi định dạng value:** phải kiểm thử client/server ở các phiên bản khác nhau.
- **Đổi default:** có thể thay đổi hành vi dù không đổi metadata được gửi; cần coi đó là thay đổi API.

Kiểm thử compatibility nên bao gồm client cũ gọi server mới, client mới gọi server cũ và các phiên bản chạy song song trong rollout. Đừng biến một metadata tùy chọn thành bắt buộc mà không có kế hoạch chuyển đổi.

## 8. Bài tập vận dụng

Một `OrderService.GetOrder` yêu cầu `x-request-id` và chấp nhận `x-locale` tùy chọn. Nhóm phát triển muốn thay đổi default locale từ `vi-VN` sang `en-US` ở phiên bản tiếp theo.

**Yêu cầu:**

1. Viết contract cho hai key, bao gồm kiểu, định dạng, số lượng value và hành vi khi vắng mặt.
2. Bổ sung unit test cho missing, empty, malformed, duplicate và supported value.
3. Viết integration test chứng minh service không chạy khi required metadata sai.
4. Xác minh optional metadata bị thiếu tạo đúng default và value hợp lệ được giữ nguyên.
5. Đề xuất cách rollout thay đổi default mà không làm client cũ bất ngờ.
6. Bổ sung test xác thực riêng để thiếu/sai credentials trả `UNAUTHENTICATED`, không bị nhầm thành lỗi metadata.

**Câu hỏi tự kiểm tra:**

- Vì sao optional metadata vắng mặt có thể dùng default nhưng value rỗng vẫn bị từ chối?
- Vì sao cần `getAll(...)` khi key phải xuất hiện đúng một lần?
- Unit test validator không chứng minh được điều gì về interceptor và service?
- Vì sao thêm metadata bắt buộc có thể phá client cũ?
- Khi nào nên trả `INVALID_ARGUMENT`, khi nào nên trả `UNAUTHENTICATED`?
- Vì sao không nên dùng metadata request ID làm cơ chế xác thực?

**Ghi nhớ:** Kiểm thử metadata phải bám theo contract của từng key: bắt buộc hay tùy chọn, định dạng, số lượng value và default. Kiểm tra cả trường hợp hợp lệ lẫn thiếu/sai/trùng; dùng unit test cho validator và integration test để chứng minh interceptor, status và service hoạt động đúng. Khi thay đổi contract, đặc biệt khi biến key tùy chọn thành bắt buộc hoặc đổi default, cần kiểm thử tương thích giữa các phiên bản client/server.
