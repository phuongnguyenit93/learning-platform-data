# Tenant ID và locale

Trong một hệ thống **Spring gRPC** phục vụ nhiều tổ chức hoặc nhiều ngôn ngữ, cùng một phương thức RPC có thể xử lý dữ liệu của các **tenant** khác nhau và trả nội dung phù hợp với **locale** của người gọi. Hai thông tin này thường được truyền qua gRPC **metadata**, nhưng có ý nghĩa rất khác nhau:

- **Tenant ID** xác định phạm vi tổ chức hoặc không gian dữ liệu đang được yêu cầu. Nó liên quan trực tiếp đến cách ly dữ liệu và kiểm soát quyền truy cập.
- **Locale** thể hiện lựa chọn ngôn ngữ và quy ước địa phương để dịch thông điệp, hiển thị số, ngày tháng hoặc đơn vị. Nó liên quan đến trải nghiệm và cách trình bày.

Ví dụ, một client gọi `OrderService.GetOrder` với `x-tenant-id: shop-a` và `x-locale: vi-VN`. Server cần xác minh người gọi có quyền truy cập `shop-a` trước khi truy vấn đơn hàng; sau đó mới dùng `vi-VN` để chọn thông điệp hiển thị. **Một metadata header do client tự gửi không phải bằng chứng có quyền truy cập tenant.**

Bài này tập trung vào cách sử dụng gRPC metadata và interceptor Java trong hệ sinh thái Spring, liên hệ với xác thực, deadline, status, TLS và kiểm thử tích hợp.

**Mục tiêu học tập:**

1. Phân biệt tenant identity, tenant selection và locale preference.
2. Chọn tên key, value ASCII và quy tắc kiểm tra `x-tenant-id`, `x-locale` hoặc `accept-language`.
3. Truyền thông tin theo từng RPC qua `Metadata` và `ClientInterceptor`.
4. Xây dựng `ServerInterceptor` kiểm tra tenant dựa trên danh tính đã xác thực, rồi chuyển ngữ cảnh qua `io.grpc.Context`.
5. Chọn locale bằng Java `Locale`, sử dụng ngôn ngữ dự phòng và tránh nhầm locale với múi giờ hoặc đơn vị tiền tệ.
6. Đảm bảo cách ly dữ liệu xuyên qua các RPC, streaming và xử lý bất đồng bộ; xây dựng kiểm thử và quan sát an toàn.

## 1. Tenant và locale giải quyết hai vấn đề khác nhau

Hãy xét một nền tảng bán hàng nhiều cửa hàng, mỗi cửa hàng là một tenant:

| Dữ liệu | Ví dụ | Tác dụng | Có thể tin trực tiếp từ client? |
| --- | --- | --- | --- |
| Tenant ID | `shop-a` | Xác định không gian dữ liệu, cấu hình hoặc chính sách của tổ chức | **Không**; cần đối chiếu danh tính và quyền |
| User identity | `user-17` | Xác định người hoặc dịch vụ đang gọi | Chỉ tin sau khi xác thực |
| Locale | `vi-VN` | Chọn bản dịch và quy ước trình bày | Có thể xem là *sở thích*, sau khi kiểm tra hợp lệ |
| Time zone | `Asia/Ho_Chi_Minh` | Chuyển đổi thời gian hiển thị | Tách biệt với locale |
| Currency | `VND` | Chỉ loại tiền hoặc quy tắc tính giá | Tách biệt với locale và cần chính sách nghiệp vụ |

Một người dùng có thể thuộc nhiều tenant. Chẳng hạn `user-17` là thành viên của `shop-a` và `shop-b`. Khi gửi `x-tenant-id: shop-b`, người dùng **đề nghị chọn tenant đang thao tác**, còn server phải kiểm tra họ có quyền ở `shop-b` và có quyền với tài nguyên được yêu cầu.

Ngược lại, `x-locale: en-US` chỉ cho biết mong muốn sử dụng tiếng Anh theo quy ước Hoa Kỳ. Người dùng ở Việt Nam vẫn có thể chọn `en-US`; locale **không xác định quốc tịch, vị trí hiện tại hay tenant**.

### Tenant isolation không chỉ là lọc giao diện

Server cần ràng buộc mọi truy vấn/ghi dữ liệu vào tenant đã được xác minh. Ví dụ khi lấy đơn hàng:

```sql
SELECT id, status, total_amount
FROM orders
WHERE tenant_id = :verifiedTenantId
  AND id = :requestedOrderId;
```

Đây là minh họa điều kiện truy vấn; hệ thống thực còn cần kiểm tra quyền đối với đơn hàng, vai trò và các chính sách liên quan. Chỉ gắn `x-tenant-id` vào log, hoặc chỉ ẩn đơn hàng của tenant khác ở client, **không tạo ra cách ly dữ liệu**.

## 2. Thiết kế các metadata key

Các tên `x-tenant-id` và `x-locale` là **quy ước do ứng dụng định nghĩa**, không phải header bắt buộc trong chuẩn gRPC. Có thể chọn tên khác, nhưng client, server, gateway và hệ thống observability phải thống nhất.

| Key | Kiểu value | Ví dụ | Gợi ý sử dụng |
| --- | --- | --- | --- |
| `x-tenant-id` | ASCII string | `shop-a` | Chỉ định tenant mong muốn trong ứng dụng đa tenant |
| `x-locale` | ASCII string | `vi-VN` | Chỉ định **một** locale theo BCP 47 |
| `accept-language` | ASCII string | `vi-VN,vi;q=0.9,en-US;q=0.7` | Thể hiện danh sách ngôn ngữ ưu tiên và trọng số |
| `authorization` | ASCII string | `Bearer <token>` | Chuyển credentials để server xác thực người gọi |
| `x-correlation-id` | ASCII string | `corr-42` | Liên kết log của những RPC cùng tác vụ |

Các key trên là metadata **ASCII** nên sử dụng `Metadata.ASCII_STRING_MARSHALLER`. Hậu tố `-bin` chỉ dùng khi value thật sự là byte nhị phân; không cần mã hóa tenant ID hoặc locale ngắn thành binary metadata.

**Quy tắc đặt tên:** dùng chữ thường với ký tự hợp lệ của gRPC metadata; không tự tạo key bắt đầu bằng `grpc-` vì tiền tố này dành riêng cho giao thức. Tránh nhét email, tên người dùng hoặc JSON dài vào metadata.

### Chọn `x-locale` hay `accept-language`?

- Dùng `x-locale` nếu hợp đồng nội bộ yêu cầu client đã chọn **một locale cụ thể**, ví dụ `vi-VN`.
- Dùng `accept-language` nếu client chỉ mô tả **danh sách ngôn ngữ chấp nhận được**, có thể kèm trọng số `q`. Server cần thực hiện bước thương lượng ngôn ngữ.
- Nếu chấp nhận cả hai key, phải xác định **thứ tự ưu tiên**, ví dụ `x-locale` từ client nội bộ được tin cậy hơn `accept-language`; không để hai giá trị mâu thuẫn dẫn đến xử lý ngẫu nhiên.

`accept-language` không phải một BCP 47 language tag duy nhất. **Không truyền cả chuỗi** `"vi-VN,vi;q=0.9,en-US;q=0.7"` vào `Locale.forLanguageTag(...)` rồi xem đó là một locale.

## 3. Định dạng tenant ID và quy tắc tin cậy

Không có một định dạng tenant ID bắt buộc cho mọi ứng dụng Spring gRPC. Có hệ thống dùng UUID, mã tổ chức hay định danh nội bộ không mang ý nghĩa nghiệp vụ. Ví dụ quy ước dùng ASCII từ 1 đến 64 ký tự, gồm chữ, số, dấu `-` và `_`:

```text
Hợp lệ theo chính sách minh họa: shop-a, tenant_07, 9d5b7e2c
Không hợp lệ:                 shop a, shop-a\nadmin, chuỗi dài bất thường
```

Quy tắc này chỉ kiểm tra **hình thức**. Một `x-tenant-id: shop-a` đúng định dạng vẫn là dữ liệu do người gọi cung cấp; không thể mặc định người đó có quyền ở `shop-a`.

Nên tách ba bước:

1. **Xác thực caller:** server kiểm tra bearer token, mTLS service identity hoặc phương án nhận dạng đã được cấu hình.
2. **Chọn và kiểm tra tenant:** nếu caller có thể thuộc nhiều tenant, đọc tenant ID được yêu cầu rồi đối chiếu tenant membership, scope, vai trò và chính sách.
3. **Phân quyền tài nguyên:** khi thực hiện `GetOrder(orderId)`, phải kiểm tra bản ghi `orderId` thuộc tenant đã được chấp nhận và caller có quyền đọc.

Một mô hình khác không cho client chọn tenant, mà **rút tenant từ claim đã được xác minh** trong token hoặc ánh xạ server-side của service account. Khi đó nên ưu tiên danh tính tenant tin cậy này; không lấy một header tùy biến để ghi đè.

| Tình huống | Quyết định hợp lý |
| --- | --- |
| Token chỉ cho phép `shop-a`, client gửi `shop-a` | Tiếp tục kiểm tra quyền trên từng thao tác |
| Token chỉ cho phép `shop-a`, client gửi `shop-b` | Từ chối truy cập, thường `PERMISSION_DENIED` |
| Caller chưa được xác thực | `UNAUTHENTICATED` |
| Header tenant thiếu ở RPC yêu cầu chọn tenant | `INVALID_ARGUMENT` hoặc quy tắc mặc định đã công bố |
| Tenant ID có ký tự sai hoặc nhiều value | `INVALID_ARGUMENT` |
| Client chỉ biết một tenant, tenant suy ra được từ principal tin cậy | Có thể không cần `x-tenant-id` |

Không nên trả thông báo phân biệt “tenant này tồn tại nhưng bạn không có quyền” với “tenant chưa tồn tại” nếu điều đó làm lộ thông tin tổ chức. Mã lỗi và mô tả phải nhất quán với chính sách tiết lộ dữ liệu.

## 4. Locale và BCP 47 language tag

Trong Java, `java.util.Locale` đại diện cho các thông tin như ngôn ngữ, khu vực và chữ viết. Trong metadata, có thể dùng **BCP 47 language tag**, ví dụ:

| Tag | Ý nghĩa |
| --- | --- |
| `vi` | Tiếng Việt, không chỉ định quốc gia |
| `vi-VN` | Tiếng Việt, khu vực Việt Nam |
| `en-US` | Tiếng Anh, khu vực Hoa Kỳ |
| `en-GB` | Tiếng Anh, khu vực Vương quốc Anh |
| `zh-Hant-TW` | Tiếng Trung dùng chữ phồn thể, khu vực Đài Loan |

Thử chuyển đổi:

```java
import java.util.Locale;

Locale vi = Locale.forLanguageTag("vi-VN");
Locale en = Locale.forLanguageTag("en-US");

System.out.println(vi.getLanguage()); // vi
System.out.println(vi.getCountry());  // VN
System.out.println(en.toLanguageTag()); // en-US
```

**Chú ý:** `Locale.forLanguageTag(...)` có thể chuẩn hóa hoặc bỏ qua những phần không hợp lệ thay vì luôn ném exception. Nếu input đến từ client và cần validate nghiêm ngặt, hãy kiểm tra định dạng, độ dài và đối chiếu với **tập locale được ứng dụng hỗ trợ**.

### Locale không đồng nghĩa với time zone

`vi-VN` không cung cấp một múi giờ chính xác cho mọi người dùng. Locale có thể dùng để chọn cách hiển thị ngày, nhưng khi diễn giải một timestamp phải có thông tin múi giờ riêng, ví dụ `Asia/Ho_Chi_Minh`. Với dữ liệu tiền tệ, `VND`, `USD` và quy tắc tính giá là những lựa chọn nghiệp vụ độc lập.

Trong API Protobuf, các timestamp nên có ngữ nghĩa thời gian rõ ràng, ví dụ `google.protobuf.Timestamp` là thời điểm tuyệt đối. Server có thể trả timestamp và mã tiền theo kiểu dữ liệu có cấu trúc, còn việc trình bày theo locale có thể thực hiện ở client. Chỉ địa phương hóa trực tiếp văn bản trả về khi hợp đồng API yêu cầu.

## 5. Phân giải locale và ngôn ngữ dự phòng

Giả sử dịch vụ chỉ hỗ trợ `vi-VN` và `en-US`. Một chính sách minh họa:

1. Nếu client gửi `x-locale` đúng tập hỗ trợ, dùng nó.
2. Nếu thiếu `x-locale` nhưng có `accept-language`, chọn locale phù hợp nhất.
3. Nếu không có lựa chọn phù hợp, dùng locale mặc định của **dịch vụ**, ví dụ `vi-VN`.
4. Nếu tổ chức có cài đặt locale mặc định riêng, áp dụng quy tắc ưu tiên sau khi tenant được xác minh, ví dụ: lựa chọn người dùng → cài đặt tenant → mặc định dịch vụ.

Ví dụ bộ chọn từ `x-locale` đã được kiểm tra:

```java
import java.util.Locale;

public final class SupportedLocales {
    public static final Locale VI_VN = Locale.forLanguageTag("vi-VN");
    public static final Locale EN_US = Locale.forLanguageTag("en-US");

    private SupportedLocales() {}

    public static Locale resolve(String localeTag) {
        if (localeTag == null || localeTag.isBlank()) {
            return VI_VN;
        }
        String normalized = Locale.forLanguageTag(localeTag).toLanguageTag();
        if ("vi-VN".equalsIgnoreCase(normalized) || "vi".equalsIgnoreCase(normalized)) {
            return VI_VN;
        }
        if ("en-US".equalsIgnoreCase(normalized) || "en".equalsIgnoreCase(normalized)) {
            return EN_US;
        }
        return VI_VN; // Fallback của dịch vụ; có thể đổi theo chính sách tenant.
    }
}
```

Với `accept-language`, Java hỗ trợ API phân tích các language range có trọng số:

```java
import java.util.List;
import java.util.Locale;

String acceptLanguage = "en-GB,en;q=0.9,vi-VN;q=0.8";
List<Locale.LanguageRange> preferences =
    Locale.LanguageRange.parse(acceptLanguage);

List<Locale> supported = List.of(
    Locale.forLanguageTag("vi-VN"),
    Locale.forLanguageTag("en-US")
);

Locale selected = Locale.lookup(preferences, supported);
if (selected == null) {
    selected = Locale.forLanguageTag("vi-VN");
}
```

Chú ý kiểm tra chuỗi đầu vào và bắt `IllegalArgumentException` từ parser theo chính sách. `Locale.lookup` dùng thuật toán tìm locale phù hợp, không đảm bảo mọi request đều có kết quả. Ví dụ trên chỉ minh họa việc xử lý ngôn ngữ chấp nhận được; không khẳng định `en-GB` có bản dịch đầy đủ hay tự biến thành `en-US` trong mọi trường hợp.

Không gọi `Locale.setDefault(...)` cho từng RPC: đó là thay đổi trạng thái mặc định ở mức JVM và có thể khiến request của tenant này ảnh hưởng request khác. Hãy truyền `Locale` theo phạm vi lời gọi.

## 6. Client interceptor: gửi tenant và locale theo từng RPC

Một ứng dụng Java/Spring gRPC có thể gắn hai giá trị vào stub bằng `CallOptions`. Interceptor đọc option khi một RPC bắt đầu, rồi ghi các header bằng `io.grpc.Metadata`. Điều này giúp tránh đặt tenant/locale của người dùng A vào một singleton stub được dùng lại cho người dùng B.

```java
import io.grpc.CallOptions;
import io.grpc.Channel;
import io.grpc.ClientCall;
import io.grpc.ClientInterceptor;
import io.grpc.ForwardingClientCall;
import io.grpc.Metadata;
import io.grpc.MethodDescriptor;
import java.util.Locale;

public final class TenantLocaleClientInterceptor implements ClientInterceptor {

    public static final CallOptions.Key<String> TENANT_OPTION =
        CallOptions.Key.create("active-tenant-id");
    public static final CallOptions.Key<Locale> LOCALE_OPTION =
        CallOptions.Key.create("active-locale");

    private static final Metadata.Key<String> TENANT_HEADER =
        Metadata.Key.of("x-tenant-id", Metadata.ASCII_STRING_MARSHALLER);
    private static final Metadata.Key<String> LOCALE_HEADER =
        Metadata.Key.of("x-locale", Metadata.ASCII_STRING_MARSHALLER);

    @Override
    public <ReqT, RespT> ClientCall<ReqT, RespT> interceptCall(
            MethodDescriptor<ReqT, RespT> method,
            CallOptions callOptions,
            Channel next) {

        ClientCall<ReqT, RespT> delegate = next.newCall(method, callOptions);
        return new ForwardingClientCall.SimpleForwardingClientCall<ReqT, RespT>(
                delegate) {
            @Override
            public void start(
                    ClientCall.Listener<RespT> listener,
                    Metadata headers) {

                String tenantId = callOptions.getOption(TENANT_OPTION);
                Locale locale = callOptions.getOption(LOCALE_OPTION);

                if (tenantId != null) {
                    headers.put(TENANT_HEADER, tenantId);
                }
                if (locale != null) {
                    headers.put(LOCALE_HEADER, locale.toLanguageTag());
                }
                super.start(listener, headers);
            }
        };
    }
}
```

Áp dụng trên một stub đã được sinh từ `.proto`:

```java
import java.util.Locale;

OrderServiceGrpc.OrderServiceBlockingStub baseStub =
    OrderServiceGrpc.newBlockingStub(channel)
        .withInterceptors(new TenantLocaleClientInterceptor());

OrderServiceGrpc.OrderServiceBlockingStub requestStub =
    baseStub
        .withOption(TenantLocaleClientInterceptor.TENANT_OPTION, "shop-a")
        .withOption(
            TenantLocaleClientInterceptor.LOCALE_OPTION,
            Locale.forLanguageTag("vi-VN"));

// requestStub.getOrder(...) gửi x-tenant-id và x-locale.
```

`OrderServiceGrpc`, `channel` và `getOrder(...)` là tên ví dụ; trong dự án thực tế, dùng stub và phương thức do Protobuf sinh ra.

**Điểm cần nhớ:** client truyền *lựa chọn tenant*, không tự chứng thực lựa chọn đó. Credentials phải được cung cấp bằng cơ chế xác thực thích hợp, ví dụ `CallCredentials`, và server chịu trách nhiệm xác minh. Interceptor trên không tự gắn token hoặc trace context.

Nếu cần truyền tenant ID của một lời gọi inbound sang lời gọi downstream, chỉ dùng **tenant ID đã được server xác minh**, không chuyển tiếp nguyên `x-tenant-id` từ client công cộng.

## 7. Server interceptor: xác thực caller và kiểm soát tenant

Một server nhận hai loại dữ liệu có mức độ tin cậy khác nhau: tenant cần gắn với **principal đã xác thực**, còn locale là sở thích có thể được thương lượng. Ví dụ dưới đây minh họa một interceptor dùng `IdentityVerifier` do ứng dụng cung cấp, nhằm tránh giả định header tenant tự đủ để phân quyền.

```java
import io.grpc.Context;
import io.grpc.Contexts;
import io.grpc.Metadata;
import io.grpc.ServerCall;
import io.grpc.ServerCallHandler;
import io.grpc.ServerInterceptor;
import io.grpc.Status;
import java.util.Iterator;
import java.util.Locale;

public final class TenantLocaleServerInterceptor implements ServerInterceptor {

    private static final Metadata.Key<String> TENANT_HEADER =
        Metadata.Key.of("x-tenant-id", Metadata.ASCII_STRING_MARSHALLER);
    private static final Metadata.Key<String> LOCALE_HEADER =
        Metadata.Key.of("x-locale", Metadata.ASCII_STRING_MARSHALLER);

    public static final Context.Key<String> VERIFIED_TENANT =
        Context.key("verified-tenant-id");
    public static final Context.Key<Locale> REQUEST_LOCALE =
        Context.key("request-locale");

    private final IdentityVerifier identityVerifier;

    public TenantLocaleServerInterceptor(IdentityVerifier identityVerifier) {
        this.identityVerifier = identityVerifier;
    }

    @Override
    public <ReqT, RespT> ServerCall.Listener<ReqT> interceptCall(
            ServerCall<ReqT, RespT> call,
            Metadata headers,
            ServerCallHandler<ReqT, RespT> next) {

        final String requestedTenant;
        final String requestedLocale;
        try {
            requestedTenant = getSingleValue(headers, TENANT_HEADER);
            requestedLocale = getSingleValue(headers, LOCALE_HEADER);
        } catch (IllegalArgumentException ex) {
            return reject(call, Status.INVALID_ARGUMENT, "Duplicate metadata");
        }

        if (requestedTenant == null
                || !requestedTenant.matches("[A-Za-z0-9_-]{1,64}")) {
            return reject(call, Status.INVALID_ARGUMENT, "Invalid tenant selection");
        }
        if (requestedLocale != null && requestedLocale.length() > 64) {
            return reject(call, Status.INVALID_ARGUMENT, "Locale too long");
        }

        final VerifiedPrincipal principal;
        try {
            // Verifier phải xác minh credentials, không tin vào x-tenant-id.
            principal = identityVerifier.verify(headers);
        } catch (InvalidCredentialsException ex) {
            return reject(call, Status.UNAUTHENTICATED, "Authentication required");
        }

        if (principal == null || !principal.canAccessTenant(requestedTenant)) {
            return reject(call, Status.PERMISSION_DENIED, "Access denied");
        }

        Locale locale = SupportedLocales.resolve(requestedLocale);
        Context context = Context.current()
            .withValue(VERIFIED_TENANT, requestedTenant)
            .withValue(REQUEST_LOCALE, locale);

        return Contexts.interceptCall(context, call, headers, next);
    }

    private static String getSingleValue(
            Metadata headers, Metadata.Key<String> key) {
        Iterable<String> all = headers.getAll(key);
        if (all == null) {
            return null;
        }
        Iterator<String> it = all.iterator();
        if (!it.hasNext()) {
            return null;
        }
        String value = it.next();
        if (it.hasNext()) {
            throw new IllegalArgumentException("Duplicate metadata key");
        }
        return value;
    }

    private static <ReqT, RespT> ServerCall.Listener<ReqT> reject(
            ServerCall<ReqT, RespT> call,
            Status status,
            String description) {
        call.close(status.withDescription(description), new Metadata());
        return new ServerCall.Listener<ReqT>() {};
    }

    public interface IdentityVerifier {
        VerifiedPrincipal verify(Metadata headers)
            throws InvalidCredentialsException;
    }

    public interface VerifiedPrincipal {
        boolean canAccessTenant(String tenantId);
    }

    public static final class InvalidCredentialsException extends Exception {
        public InvalidCredentialsException(String message) {
            super(message);
        }
    }
}
```

Trong ví dụ:

- `getSingleValue(...)` từ chối header trùng để tránh hai cách diễn giải tenant/locale khác nhau.
- `IdentityVerifier` là **điểm tích hợp** với xác thực thực tế, không phải một verifier hoàn chỉnh. Nó phải kiểm tra chữ ký, hiệu lực, audience/issuer của JWT hoặc dùng cơ chế xác thực thích hợp; không chỉ đọc một claim chưa xác minh.
- `principal.canAccessTenant(...)` phải dựa vào quyền được chứng thực hoặc một nguồn phân quyền tin cậy. Nếu phân quyền thay đổi theo thời gian, cần chính sách đồng bộ và thu hồi phù hợp.
- `SupportedLocales.resolve(...)` được định nghĩa ở mục trước; locale không quyết định có quyền truy cập tenant hay không.
- `Contexts.interceptCall(...)` chuyển tenant đã xác minh và locale đã chọn vào context gRPC của lời gọi.

**Giới hạn của ví dụ:** interceptor chỉ kiểm tra membership cơ bản. Việc người dùng được phép đọc/ghi **một tài nguyên cụ thể** vẫn phải được thực hiện ở service hoặc policy layer. Đối với verifier cần gọi dịch vụ mạng, tránh thực hiện thao tác blocking kéo dài trên thread xử lý gRPC; sử dụng cơ chế xác thực bất đồng bộ hoặc thành phần hạ tầng phù hợp.

## 8. Dùng tenant và locale trong service

Code xử lý RPC đọc **tenant đã xác minh** và locale từ `io.grpc.Context`:

```java
import java.util.Locale;

String tenantId = TenantLocaleServerInterceptor.VERIFIED_TENANT.get();
Locale locale = TenantLocaleServerInterceptor.REQUEST_LOCALE.get();

if (tenantId == null) {
    responseObserver.onError(
        Status.UNAUTHENTICATED
            .withDescription("Authentication required")
            .asRuntimeException());
    return;
}

// Truy vấn bắt buộc giới hạn theo tenant đã kiểm tra.
Order order = orderRepository.findByTenantIdAndId(
    tenantId, request.getOrderId());

if (order == null || !orderAccessPolicy.canRead(tenantId, request.getOrderId())) {
    responseObserver.onError(
        Status.NOT_FOUND.withDescription("Order not found")
            .asRuntimeException());
    return;
}

// locale được dùng ở tầng bản dịch/hiển thị phù hợp với hợp đồng API.
```

Đây là đoạn minh họa trong RPC method: `orderRepository` và `orderAccessPolicy` là các thành phần ứng dụng cần triển khai. Quyết định trả `NOT_FOUND` cho tài nguyên không có quyền truy cập là một **chính sách che giấu sự tồn tại**; API khác có thể dùng `PERMISSION_DENIED`. Không được vô tình trả dữ liệu cross-tenant chỉ vì caller biết `orderId`.

### Locale có thể ảnh hưởng response như thế nào?

Ví dụ một thông báo nghiệp vụ:

| Locale | Thông báo |
| --- | --- |
| `vi-VN` | “Đơn hàng đã được xác nhận” |
| `en-US` | “Order confirmed” |

Trong Java/Spring, có thể sử dụng `MessageSource` để lấy bản dịch theo locale:

```java
import java.util.Locale;
import org.springframework.context.MessageSource;

Locale locale = TenantLocaleServerInterceptor.REQUEST_LOCALE.get();
if (locale == null) {
    locale = Locale.forLanguageTag("vi-VN");
}

String message = messageSource.getMessage(
    "order.confirmed",
    null,
    locale);
```

`messageSource` giả định đã được cấu hình với các bản dịch tương ứng. Đây là một lựa chọn cho **nội dung cần địa phương hóa**; nhiều API gRPC nên trả mã trạng thái và trường dữ liệu Protobuf ổn định, để client tự hiển thị bản dịch. Không sử dụng văn bản đã dịch làm mã lỗi máy đọc.

### Locale trong Java, Spring và các thread

`io.grpc.Context`, `org.springframework.context.i18n.LocaleContextHolder` và `org.slf4j.MDC` không phải cùng một cơ chế. Việc đặt `REQUEST_LOCALE` trong gRPC Context không tự động thay đổi `LocaleContextHolder` trên mọi thread.

Khi dùng Spring API dựa vào `LocaleContextHolder`, cần đặt và khôi phục locale trong phạm vi callback/transaction theo cách phù hợp với ứng dụng. Tránh quên khôi phục trạng thái trên thread pool. Đối với xử lý bất đồng bộ, cần chuyển context gRPC (`Context.current().wrap(...)` hoặc executor tương ứng) và, nếu có, cả Spring locale/trace context một cách có chủ đích.

## 9. Chuyển tenant và locale giữa các service

Giả sử `CheckoutService` gọi `InventoryService` để trừ tồn kho. Hai dịch vụ cần thống nhất tenant nào là chủ dữ liệu và giao tiếp ngôn ngữ nào được chọn.

```text
Client
  |
  | x-tenant-id: shop-a
  | x-locale: vi-VN
  v
CheckoutService
  | xác thực caller
  | đối chiếu quyền với shop-a
  | active tenant = shop-a
  | request locale = vi-VN
  |
  | RPC downstream; credentials/service identity phù hợp
  | x-tenant-id: shop-a  <- tenant đã kiểm tra
  | x-locale: vi-VN      <- sở thích đã chọn
  v
InventoryService
  | xác thực caller là CheckoutService/delegated caller
  | tự kiểm tra quyền đối với shop-a
  v
Truy vấn/ghi dữ liệu của shop-a
```

**Chính sách quan trọng:**

1. Downstream service **không bỏ qua kiểm tra quyền** chỉ vì một upstream đã gắn `x-tenant-id`. Nó phải xác thực caller và kiểm tra quyền theo ranh giới tin cậy của mình.
2. Nếu token của người dùng bị giới hạn `audience`, không mặc định chuyển nguyên token đó tới mọi dịch vụ. Có thể cần service identity, token exchange hoặc cơ chế on-behalf-of phù hợp.
3. Locale có thể truyền tiếp để tạo thông điệp phù hợp, nhưng không bao giờ là căn cứ cấp quyền.
4. Nếu tạo một tác vụ độc lập hoặc thay tenant khi xử lý, phải xác định rõ context mới thay vì dùng nhầm tenant cũ.
5. Deadline, trace context và correlation ID vẫn được thiết kế theo API tương ứng; tenant/locale metadata không thay thế chúng.

### Streaming RPC

Metadata chỉ được gửi lúc **bắt đầu RPC stream**. Vì vậy:

- Trong một stream cùng tenant, mọi message được xử lý theo tenant đã kiểm tra tại thời điểm mở stream và các chính sách thu hồi/quyền trong suốt stream.
- Không kỳ vọng sửa `x-tenant-id` hoặc `x-locale` giữa các message mà client đã gửi.
- Nếu nghiệp vụ cho phép mỗi message thuộc tenant khác, cần thiết kế tenant thành trường của message Protobuf **và kiểm tra quyền trên từng message**. Đây là quyết định hợp đồng và bảo mật cần được xem xét kỹ.
- Với stream kéo dài, cần chính sách về token hết hạn, quyền bị thu hồi, kiểm tra hủy và deadline.

## 10. Trạng thái lỗi, logging và bảo mật

Vấn đề tenant và locale có thể dẫn đến nhiều loại kết quả khác nhau:

| Tình huống | gRPC status phù hợp | Ghi chú |
| --- | --- | --- |
| Không có hoặc token không hợp lệ | `UNAUTHENTICATED` | Chưa xác thực được caller |
| Tenant ID có định dạng sai hoặc header trùng | `INVALID_ARGUMENT` | Input metadata không hợp lệ |
| Caller đã xác thực nhưng thiếu quyền trên tenant | `PERMISSION_DENIED` | Không đủ quyền truy cập |
| Tài nguyên thuộc tenant khác | `PERMISSION_DENIED` hoặc `NOT_FOUND` | Theo chính sách che giấu tài nguyên |
| Locale không hỗ trợ | Locale fallback hoặc `INVALID_ARGUMENT` | Chọn một chính sách nhất quán trong hợp đồng |
| Dịch vụ phân quyền phụ thuộc hạ tầng và đang unavailable | `UNAVAILABLE` hoặc trạng thái hạ tầng thích hợp | Không được mở quyền khi backend kiểm tra thất bại |
| RPC vượt deadline | `DEADLINE_EXCEEDED` | Deadline được quản lý qua API gRPC |

Các kết quả trên được trả bằng `io.grpc.Status`. Không tự ghi `grpc-status` như một custom metadata key.

**Logging:** ghi tenant ID đã được xác minh chỉ khi chính sách lưu log cho phép, ưu tiên mã định danh không tiết lộ dữ liệu riêng tư. Locale có thể hữu ích cho chẩn đoán lỗi bản dịch, nhưng không tạo metric label có số lượng giá trị không kiểm soát. Không ghi bearer token, danh sách tenant của người dùng hoặc toàn bộ metadata vào log.

**Bảo mật trên đường truyền:** TLS/mTLS bảo vệ kết nối và giúp xác thực dịch vụ theo cấu hình; chúng không làm cho một tenant ID tự khai trở thành dữ liệu đã được phân quyền. Nếu có gateway/proxy kết thúc TLS, cần xác định ranh giới tin cậy, bảo vệ header nội bộ và xác thực kết nối phía sau proxy.

**Giới hạn kích thước:** gRPC metadata được vận chuyển qua HTTP/2 headers/trailers nên chịu giới hạn dung lượng của thư viện và hạ tầng. Tenant ID và locale nên ngắn; không đưa danh sách quyền hoặc cấu hình tenant lớn vào metadata.

## 11. Kiểm thử tích hợp trong Spring gRPC

Có thể kiểm tra logic `Metadata` và resolver bằng unit test, sau đó chạy client/server gRPC có đăng ký interceptor để xác nhận quyền, context và response. `InProcessServerBuilder`/`InProcessChannelBuilder` hữu ích khi kiểm thử logic không cần cổng mạng; TLS, proxy và sự cố mạng cần thử trên transport thật.

| Ca kiểm thử | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Tenant hợp lệ, caller được cấp quyền | Principal của `shop-a`, header `shop-a` | RPC xử lý trong phạm vi `shop-a` |
| Thiếu credentials | Có `x-tenant-id` nhưng không có token hợp lệ | `UNAUTHENTICATED` |
| Tenant sai quyền | Caller `shop-a` gửi `shop-b` | `PERMISSION_DENIED` |
| Header tenant trùng | Hai giá trị `x-tenant-id` | `INVALID_ARGUMENT` trong ví dụ interceptor |
| Tenant sai định dạng | Có ký tự newline hoặc độ dài quá giới hạn | Bị từ chối theo chính sách |
| Đọc tài nguyên cross-tenant | Yêu cầu ID đơn của tenant khác | Không trả dữ liệu; mã lỗi theo policy |
| Locale hợp lệ | `x-locale: en-US` | Context có `Locale.forLanguageTag("en-US")` |
| Locale không được hỗ trợ | `x-locale: fr-FR` | Dùng fallback `vi-VN` theo ví dụ |
| Thiếu locale | Không có `x-locale` | Dùng locale mặc định theo chính sách |
| `accept-language` có trọng số | `en-GB,en;q=0.9,vi-VN;q=0.8` | Resolver thương lượng theo danh sách hỗ trợ |
| Hai caller đồng thời | Khác tenant và locale trên cùng channel | Không rò rỉ context giữa hai RPC |
| RPC downstream | Đã xác minh tenant ở upstream | Downstream vẫn xác thực và kiểm tra quyền |
| Streaming | Nhiều message trong một stream | Tenant/locale gắn với RPC, không nhầm per-message |
| Async executor | Chuyển xử lý sang thread pool | Context được chuyển đúng, không ảnh hưởng request khác |
| Kiểm tra log | Bật tracing và logging trong test | Không lộ token hoặc metadata nhạy cảm |

### Ví dụ unit test cho locale resolver

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import java.util.Locale;
import org.junit.jupiter.api.Test;

class SupportedLocalesTest {

    @Test
    void resolvesSupportedLocaleAndFallsBack() {
        assertEquals(
            Locale.forLanguageTag("en-US"),
            SupportedLocales.resolve("en-US"));
        assertEquals(
            Locale.forLanguageTag("vi-VN"),
            SupportedLocales.resolve("vi"));
        assertEquals(
            Locale.forLanguageTag("vi-VN"),
            SupportedLocales.resolve("fr-FR"));
        assertEquals(
            Locale.forLanguageTag("vi-VN"),
            SupportedLocales.resolve(null));
    }
}
```

Test này kiểm tra resolver thuần Java. Để xác nhận interceptor tạo `VERIFIED_TENANT` đúng, cần test qua server có **IdentityVerifier giả lập với principal và quyền xác định**. Đừng chỉ khẳng định một header đã được gửi là đủ để chứng minh isolation; hãy kiểm tra rằng truy vấn từ tenant A không bao giờ trả bản ghi tenant B.

## 12. Bài tập thực hành: gRPC đa tenant, đa ngôn ngữ

Một nền tảng SaaS có `BillingService.GetInvoice` cho ba tenant: `shop-a`, `shop-b` và `shop-c`. Client cho phép người dùng chọn cửa hàng và ngôn ngữ hiển thị. Dữ liệu hóa đơn được lưu riêng theo tenant.

**Yêu cầu triển khai:**

1. Thống nhất `x-tenant-id` là tenant ID dạng ASCII, `x-locale` là một BCP 47 tag. Ghi rõ định dạng, giới hạn, chính sách thiếu key và chính sách fallback.
2. Gắn hai metadata value vào client stub theo từng RPC, đồng thời truyền credentials qua cơ chế xác thực phù hợp.
3. Tại server, kiểm tra caller đã xác thực và được phép thao tác tenant yêu cầu; đặt **verified tenant** và locale vào context.
4. Truy vấn hóa đơn với cả tenant ID đã xác minh và invoice ID, sau đó áp dụng policy xem hóa đơn.
5. Trả số tiền và timestamp dưới dạng dữ liệu có cấu trúc. Chỉ địa phương hóa thông điệp mà hợp đồng API thực sự yêu cầu.
6. Viết test cho tenant không hợp lệ, truy cập cross-tenant, locale được/không được hỗ trợ, xử lý đồng thời và một lời gọi streaming.

**Câu hỏi tự kiểm tra:**

- Vì sao `x-tenant-id` chỉ là một yêu cầu chọn tenant, không phải bằng chứng được phép truy cập?
- Một người dùng thuộc hai tenant cần làm gì để truy cập tài nguyên của từng tenant?
- Khi nào nên không cho client gửi tenant ID mà lấy trực tiếp từ principal đã xác minh?
- `vi-VN` có xác định chắc chắn múi giờ hoặc đơn vị tiền tệ của một giao dịch không?
- Khác biệt giữa `x-locale: vi-VN` và `accept-language: vi-VN,vi;q=0.9,en-US;q=0.7` là gì?
- Vì sao không sử dụng `Locale.setDefault(...)` mỗi khi nhận RPC?
- Nếu `CheckoutService` đã xác minh tenant A, `InventoryService` có được tin mọi header tenant mà nó nhận không?
- Trong bidirectional streaming, liệu client có thể tự đổi tenant bằng cách “cập nhật metadata” ở message thứ hai không?

**Ghi nhớ:** Tenant ID và locale cùng có thể xuất hiện trong gRPC metadata nhưng phục vụ hai mục tiêu khác nhau. **Tenant ID xác định phạm vi dữ liệu cần kiểm soát quyền**, trong khi **locale điều chỉnh cách trình bày theo ngôn ngữ và quy ước địa phương**. Với Spring gRPC, hãy truyền chúng bằng metadata và interceptor theo từng RPC, kiểm tra tenant dựa trên principal tin cậy, lưu ngữ cảnh trong `io.grpc.Context` và kiểm thử cả ranh giới dữ liệu lẫn cơ chế fallback ngôn ngữ.
