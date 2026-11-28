# Fail closed

## 1. Không biến lỗi kiểm soát thành quyền truy cập

Một API xuất hồ sơ khách hàng gọi dịch vụ phân quyền trước khi đọc dữ liệu. Khi dịch vụ phân quyền timeout, lập trình viên cho API tiếp tục để “không ảnh hưởng người dùng”. Nếu người gọi vốn không được phép xuất hồ sơ, timeout đã trở thành một cách vượt qua kiểm soát.

**Fail closed** tại một ranh giới bảo mật nghĩa là: khi hệ thống không thiết lập được các điều kiện cần để cho phép một hành động, nó không thực hiện hành động được bảo vệ đó và không phát hành dữ liệu tương ứng.

Điều cần giữ là bất biến bảo mật, không chỉ một mã lỗi trên giao diện. Trả HTTP 403 sau khi đã xuất file hoặc gửi lệnh thanh toán không làm cho luồng trở thành fail closed.

Trong chương Error handling, chủ đề này liên kết trực tiếp với việc đặc tả xác thực, phân quyền, dữ liệu, logging và phục hồi. Yêu cầu phải chỉ rõ khi một thành phần lỗi, quyền nào vẫn được chứng minh, hành động nào bị chặn, dữ liệu nào không được phát hành và bằng chứng nào xác nhận hành vi đó.

Sau bài học, người học có thể:

- Phân biệt quyết định từ chối với việc chưa xác định được quyền.
- Viết bất biến và yêu cầu fail closed có thể kiểm chứng.
- Phân tích fallback, cache, circuit breaker và chế độ suy giảm.
- Đặt kiểm soát trước tác động phụ và xử lý kết quả chưa xác định.
- Thiết kế ca lỗi, phục hồi và truy vết yêu cầu tới bằng chứng.

## 2. Fail closed, fail open và trạng thái an toàn

### 2.1. Hai cách phản ứng tại cùng một cổng kiểm soát

Giả sử điều kiện để tải tài liệu là có quyết định cho phép hợp lệ cho đúng người, tenant, tài liệu và hành động.

| Tình trạng | Fail closed | Fail open |
|---|---|---|
| Có quyết định cho phép hợp lệ | Cho phép trong phạm vi quyết định | Cho phép trong phạm vi quyết định |
| Có quyết định từ chối | Không phát hành tài liệu | Thông thường vẫn từ chối theo thiết kế ban đầu |
| Dịch vụ phân quyền timeout | Không tải tài liệu nếu không có căn cứ hợp lệ khác | Tiếp tục tải vì không nhận được quyết định từ chối |
| Quyết định sai định dạng hoặc thiếu trường bắt buộc | Không coi là được phép | Có thể vô tình dùng giá trị mặc định cho phép |

Điểm khác biệt nằm ở cách đối xử với **sự thiếu chắc chắn**. “Chưa nhận được DENY” không có nghĩa là “đã có ALLOW”.

### 2.2. Fail closed không có nghĩa là tắt toàn bộ hệ thống

Nếu việc xuất dữ liệu riêng tư phụ thuộc vào dịch vụ phân quyền đang lỗi, chức năng xuất có thể phải dừng. Trang hướng dẫn công khai hoặc một chức năng độc lập vẫn có thể hoạt động theo chính sách của chính chúng.

Cần xác định phạm vi theo hành động và điều kiện bảo mật. Một chế độ suy giảm hợp lệ giữ được các bất biến đã xác định; nó không dùng sự cố làm lý do để cấp thêm quyền.

Chế độ “chỉ đọc” cũng không mặc nhiên an toàn. Đọc một hồ sơ, tải file hoặc xem danh sách tài khoản đều có thể làm lộ dữ liệu. Nếu điều kiện bảo vệ dữ liệu chưa được thiết lập, chuyển từ ghi sang đọc chưa giải quyết được vấn đề.

### 2.3. Phân biệt với fail-safe nói chung

Fail closed tập trung vào việc giữ ranh giới quyền truy cập hoặc điều kiện bảo mật khi thất bại. “Trạng thái an toàn” của một hệ thống rộng hơn có thể còn phụ thuộc vào tính toàn vẹn, sẵn sàng và yêu cầu an toàn của miền nghiệp vụ.

Không suy ra rằng chặn mọi thao tác luôn là lựa chọn đúng cho mọi hệ thống. Cần phân tích thuộc tính nào được bảo vệ và hậu quả của trạng thái suy giảm. Trong bài này, mỗi yêu cầu đều gắn với một hành động bảo mật cụ thể thay vì áp một khẩu hiệu cho toàn bộ sản phẩm.

## 3. Đặc tả bất biến trước khi chọn fallback

### 3.1. Một bất biến phân quyền minh họa

```text
Nếu hệ thống phát hành tài liệu được bảo vệ,
thì phải có căn cứ cho phép hợp lệ cho:
  đúng chủ thể,
  đúng tenant,
  đúng tài nguyên và phiên bản/ngữ cảnh cần thiết,
  đúng hành động,
  trong thời hạn và điều kiện chính sách được chấp nhận.
```

Căn cứ hợp lệ không chỉ là một chuỗi `ALLOW`. Nó còn phải đến từ nguồn được tin cậy, được ràng buộc với request và đáp ứng các điều kiện cần thi hành.

Ví dụ, quyết định cho người A đọc tài liệu X không cho phép người B đọc X, không cho phép A sửa X và không cho phép A đọc Y. Một decision cache chỉ dùng tên endpoint làm khóa sẽ không bảo toàn bất biến này.

### 3.2. Tách ba trạng thái quyết định

Một giao diện phân quyền nên phân biệt rõ:

| Trạng thái | Ý nghĩa | Hành vi tại hành động được bảo vệ |
|---|---|---|
| ALLOW | Đã thiết lập đủ điều kiện cho phép trong phạm vi cụ thể | Thi hành đúng phạm vi và mọi điều kiện kèm theo |
| DENY | Đã đánh giá và xác định không cho phép | Không thực hiện hành động |
| INDETERMINATE | Không thể đưa ra quyết định có căn cứ | Không tự nâng thành ALLOW |

Timeout, mất kết nối, policy thiếu, thuộc tính bắt buộc không có, quyết định hết hạn hoặc không xác thực được nguồn đều có thể làm kết quả không xác định theo hợp đồng.

Không gộp `INDETERMINATE` vào `DENY` trong mọi dữ liệu vận hành. Hai trạng thái có thể cùng chặn hành động nhưng cần cảnh báo, khả năng retry và chẩn đoán khác nhau.

Phản hồi công khai vẫn phải theo hợp đồng của luồng, bao gồm chính sách không làm lộ sự tồn tại của tài khoản hoặc tài nguyên. Không nhất thiết đưa toàn bộ trạng thái nội bộ cho client.

### 3.3. ALLOW có thể kèm điều kiện phải thi hành

Một quyết định có thể chỉ cho phép xem một số field, giới hạn số bản ghi hoặc yêu cầu một sự kiện audit bền vững trước khi xuất dữ liệu.

Nếu không áp dụng được các điều kiện đó, không được giữ nhãn ALLOW rồi trả toàn bộ dữ liệu. Việc thi hành điều kiện là một phần của căn cứ cho phép.

## 4. Các đường lỗi có thể làm mở quyền

### 4.1. Fallback vô tình trở thành cơ chế cấp quyền

Những mẫu nguy hiểm thường gặp:

```java
try {
    return policyClient.isAllowed(context);
} catch (Exception failure) {
    return true; // Lỗi kiểm tra đã trở thành quyền truy cập.
}
```

```text
Không đọc được role -> dùng role mặc định là administrator.
Không có tenant -> truy vấn không kèm điều kiện tenant.
Không kiểm tra được chữ ký -> chỉ đọc phần payload rồi tin nó.
Không lấy được khóa mã hóa -> lưu bản rõ để tiếp tục xử lý.
Không ghi được audit bắt buộc -> bỏ qua audit và vẫn xuất dữ liệu.
```

Mỗi dòng làm mất một điều kiện bảo mật khi điều kiện đó khó thiết lập nhất.

Một lỗi tương tự xuất hiện khi parser chuyển quyết định thiếu trường thành object có `allowed = true`, hoặc khi code chỉ kiểm tra `decision != DENY`. Cần xác nhận ALLOW hợp lệ một cách tường minh.

### 4.2. Mô hình rủi ro theo nguyên nhân và hậu quả

| ID | Điều kiện và hành vi | Hậu quả có thể xảy ra |
|---|---|---|
| R-FC-01 | Policy service timeout, fallback cho phép | Người không có quyền thực hiện hành động được bảo vệ |
| R-FC-02 | Tenant context thiếu làm bỏ bộ lọc dữ liệu | Dữ liệu của tenant khác được đọc hoặc thay đổi |
| R-FC-03 | Cache chứa ALLOW cũ sau thay đổi quyền | Quyền đã thu hồi tiếp tục được sử dụng ngoài giới hạn chấp nhận |
| R-FC-04 | Kiểm tra quyền chạy sau tác động phụ | Response lỗi nhưng giao dịch hoặc thông điệp đã được phát hành |
| R-FC-05 | Queue hoặc retry chạy dưới một principal mặc định quá rộng | Công việc thực hiện với quyền lớn hơn quyền đã thiết lập |
| R-FC-06 | Phục hồi tự bật chức năng trước khi kiểm tra cấu hình | Bản triển khai hoạt động với policy, khóa hoặc trạng thái quyền không phù hợp |

Kịch bản nên nêu hành động cụ thể. Câu “hệ thống có thể fail open” không đủ để lựa chọn kiểm soát và ca thử.

## 5. Yêu cầu fail closed có thể kiểm chứng

Một yêu cầu nên trả lời được: cổng kiểm soát nào, đầu vào nào, lỗi nào, điều gì bị chặn, trạng thái gì được phép và bằng chứng ở đâu.

| ID | Yêu cầu minh họa | Bằng chứng nghiệm thu |
|---|---|---|
| FC-01 | Chỉ thực hiện hành động được bảo vệ khi có căn cứ ALLOW hợp lệ cho đúng ngữ cảnh | Hợp đồng quyết định và thử sai chủ thể, tenant, tài nguyên, hành động |
| FC-02 | Timeout, lỗi nguồn, kết quả null hoặc sai định dạng không được tạo ALLOW | Fault injection tại client và bộ giải mã quyết định |
| FC-03 | Thiếu danh tính hoặc thuộc tính bắt buộc không được thay bằng quyền cao hoặc phạm vi toàn cục | Thử thiếu từng thành phần context |
| FC-04 | Quyết định DENY không bị retry, fallback hoặc circuit breaker chuyển thành cho phép | Kịch bản từ chối kết hợp các nhánh dự phòng |
| FC-05 | Kiểm soát được thi hành trước khi phát hành dữ liệu hoặc tạo tác động phụ thuộc phạm vi | Quan sát response, database, queue và dependency giả lập |
| FC-06 | Chỉ dùng decision cache khi xác minh được nguồn, phạm vi, thời hạn và điều kiện chấp nhận của policy | Thử hết hạn, sai khóa, thu hồi và cache không khả dụng |
| FC-07 | Chế độ suy giảm có danh sách hành động và căn cứ cho phép riêng; không tự mở rộng quyền khi lỗi | Ma trận hành vi suy giảm và thử từng hành động |
| FC-08 | Không chuyển sang lưu hoặc truyền bản rõ khi điều kiện mã hóa bắt buộc chưa thiết lập được | Thử lỗi cung cấp khóa và quan sát các nơi lưu hoặc gửi |
| FC-09 | Nếu audit bền vững là điều kiện bắt buộc trước hành động, không thực hiện hành động khi chưa đáp ứng điều kiện đó | Thử sink và đường lưu đệm được chấp nhận cùng bị lỗi |
| FC-10 | Job, consumer và retry dùng quyền được xác định cho thời điểm thực hiện theo policy | Thử quyền thay đổi, job cũ và principal không hợp lệ |
| FC-11 | Phục hồi xác minh lại các điều kiện cần thiết trước khi mở hành động được bảo vệ | Diễn tập phục hồi và lịch sử trạng thái |
| FC-12 | Trạng thái chưa xác định sau một thao tác ghi không được báo là chắc chắn chưa xảy ra hoặc tự thực hiện lại không kiểm soát | Thử timeout sau commit và cơ chế đối soát hoặc idempotency |

Đây là bộ yêu cầu mẫu. Danh mục action, thời hạn, môi trường và chủ sở hữu phải được chốt cho từng sản phẩm; bản thân bảng chưa phải bằng chứng đáp ứng.

### 5.1. Đặc tả sâu hơn cho FC-02 và FC-05

```text
Phạm vi:
  API xuất báo cáo riêng tư của tenant trong candidate build.

Điều kiện cần:
  Danh tính đã được xác minh.
  Tenant và tài nguyên được xác định từ ngữ cảnh tin cậy.
  Có quyết định cho phép hợp lệ cho hành động export.

Khi không thiết lập được quyết định:
  Không tạo file báo cáo có dữ liệu được bảo vệ.
  Không cấp URL tải, không gửi byte dữ liệu báo cáo cho client.
  Không enqueue job xuất dưới principal mặc định để bỏ qua kiểm tra.
  Trả lỗi theo hợp đồng và ghi sự kiện tối thiểu không chứa secret.

Điều kiện kiểm chứng:
  Lỗi kiểm tra quyền đã thực sự được kích hoạt.
  Không có tác động bị cấm tại các đầu ra đã liệt kê.
  Không chỉ dựa vào status HTTP để kết luận đạt.
```

Nếu hệ thống cho phép tiếp nhận một yêu cầu chưa được phép thực hiện, cần đặc tả thao tác tiếp nhận như một hành động riêng với quyền, dữ liệu và trạng thái riêng. Không được mô tả một lệnh đã sẵn sàng chạy đặc quyền là “chỉ enqueue” để bỏ qua kiểm soát.

## 6. Vị trí thực thi trong kiến trúc

### 6.1. Cổng kiểm soát phải nằm trước hành động được bảo vệ

```text
Nhận request
  -> xác minh danh tính và tạo context tin cậy
  -> lấy hoặc tính quyết định
  -> kiểm tra hiệu lực, phạm vi và điều kiện
      -> DENY / INDETERMINATE: không thực hiện hành động
      -> ALLOW hợp lệ: thực hiện trong đúng phạm vi
  -> ánh xạ kết quả và lỗi công khai
```

Không phát hành một phần dữ liệu trong lúc chờ quyết định cuối cùng. Điều này đặc biệt quan trọng với stream, tải file và export: những byte đã tới client không thể được thu hồi bằng một status lỗi gửi sau đó.

Những thao tác cần để đánh giá quyền, chẳng hạn đọc policy hoặc metadata được phép, khác với thao tác nghiệp vụ đang được bảo vệ. Yêu cầu cần phân biệt hai nhóm để không vô tình cấm chính việc đánh giá, đồng thời không gọi một bước đọc dữ liệu nhạy cảm là “metadata” để né kiểm soát.

### 6.2. Bảo toàn context đến nơi sử dụng dữ liệu

Kiểm tra đúng ở gateway chưa đủ nếu service phía sau bỏ tenant hoặc tin một header do client tự gửi. Phải xác định nguồn tạo context, cách truyền và thành phần được quyền thay đổi nó.

Tại nơi đọc hoặc ghi dữ liệu, ràng buộc tài nguyên và tenant phải khớp với phạm vi đã được phép. Ví dụ, truy vấn tài liệu cần dùng cả định danh tài liệu và tenant phù hợp thay vì chỉ dùng một ID từ request rồi hy vọng gateway đã xử lý.

Không kiểm tra tài liệu X rồi sử dụng tham số có thể thay đổi để đọc Y. Context bất biến và điều kiện tại tầng dữ liệu giúp giảm khoảng cách giữa kiểm tra và sử dụng, nhưng không tự giải quyết mọi thay đổi trạng thái đồng thời.

### 6.3. Thời điểm quyền có hiệu lực phải được định nghĩa

Với thao tác dài, cần chốt quyền được đánh giá ở thời điểm nào: khi nhận lệnh, khi bắt đầu xử lý, trước khi phát hành kết quả hay theo từng giai đoạn. Chính sách thu hồi quyền quyết định mức kiểm tra lại cần thiết.

Không thể chỉ ghi “quyền luôn mới nhất” mà không thiết kế cơ chế nhất quán và giới hạn trễ. Nếu hệ thống phân tán chấp nhận một khoảng trễ thu hồi, khoảng đó phải là lựa chọn chính sách có đo lường và được phản ánh trong hợp đồng quyết định.

## 7. Ví dụ Java: chỉ ALLOW hợp lệ mới đi qua cổng

Ví dụ sau dùng cú pháp Java 17 trở lên và minh họa cổng thực thi. Hợp đồng của `Authorizer` là trả quyết định đã được xác minh nguồn, phạm vi và hiệu lực cho đúng context; cổng không nhận một chuỗi ALLOW tùy ý từ client.

```java
import java.util.Objects;
import java.util.UUID;

public final class FailClosedGate {
    private FailClosedGate() {}

    public enum Action {
        READ_DOCUMENT,
        EXPORT_REPORT
    }

    public enum Outcome {
        ALLOW,
        DENY,
        INDETERMINATE
    }

    public record Context(
        UUID subjectId,
        UUID tenantId,
        UUID resourceId,
        Action action
    ) {
        public Context {
            Objects.requireNonNull(subjectId);
            Objects.requireNonNull(tenantId);
            Objects.requireNonNull(resourceId);
            Objects.requireNonNull(action);
        }
    }

    public record Decision(Outcome outcome) {}

    public interface Authorizer {
        Decision evaluate(Context context) throws DecisionUnavailable;
    }

    public static final class DecisionUnavailable extends Exception {}

    public static final class AccessDenied extends RuntimeException {
        public AccessDenied() {
            super("ACCESS_DENIED");
        }
    }

    public static final class AuthorizationNotEstablished
            extends RuntimeException {
        public AuthorizationNotEstablished() {
            super("AUTHORIZATION_NOT_ESTABLISHED");
        }
    }

    public static void requirePermission(
        Context context,
        Authorizer authorizer
    ) {
        Objects.requireNonNull(context);
        Objects.requireNonNull(authorizer);

        Decision decision;
        try {
            decision = authorizer.evaluate(context);
        } catch (DecisionUnavailable failure) {
            throw new AuthorizationNotEstablished();
        }

        if (decision == null || decision.outcome() == null) {
            throw new AuthorizationNotEstablished();
        }

        switch (decision.outcome()) {
            case ALLOW -> {
                return;
            }
            case DENY -> throw new AccessDenied();
            case INDETERMINATE ->
                throw new AuthorizationNotEstablished();
            default -> throw new AuthorizationNotEstablished();
        }
    }
}
```

Luồng sử dụng ở mức minh họa:

```java
// context được tạo từ danh tính và phạm vi đã xác minh ở server.
FailClosedGate.requirePermission(context, authorizer);

// Chỉ đến bước này sau khi cổng thành công.
return repository.readDocument(
    context.tenantId(),
    context.resourceId()
);
```

Những điểm cần giữ khi tích hợp:

- Không bắt `AccessDenied` hoặc `AuthorizationNotEstablished` rồi tiếp tục gọi repository.
- Không đặt thao tác được bảo vệ trong `finally`.
- Không dùng nhánh fallback của circuit breaker để trả quyền cho phép mặc định.
- Lỗi bất ngờ khác từ authorizer phải đi tới ranh giới xử lý lỗi an toàn, không dẫn sang đường thực hiện nghiệp vụ.
- Adapter lỗi chọn status và nội dung công khai theo hợp đồng, không serialize exception thô.
- Request ID và sự kiện nội bộ giúp phân biệt bị từ chối với dependency không khả dụng mà không phát hành secret.

### 7.1. Những điều ví dụ chưa chứng minh

Kiểu `Decision` tối giản không tự chứng minh nguồn quyết định, chữ ký, độ mới hoặc nghĩa vụ kèm theo. Những điều đó là trách nhiệm của triển khai `Authorizer` theo hợp đồng, và cần ca kiểm thử riêng.

Tương tự, UUID của subject hoặc tenant không tự chứng minh người gọi sở hữu danh tính đó. Nếu lấy các UUID thô từ request rồi gắn vào context tin cậy, lỗi nằm trước cổng.

Ví dụ cũng chưa xử lý mọi tranh chấp giữa kiểm tra và sử dụng, truy cập dữ liệu đồng thời hoặc quyền thay đổi giữa một job dài. Không dùng đoạn mã này làm bằng chứng cho các thuộc tính mà nó không triển khai.

## 8. Cache, quyền ngoại tuyến và chính sách thu hồi

### 8.1. Cache không tự đồng nghĩa fail open

Một quyết định cache có thể là căn cứ hợp lệ nếu chính sách cho phép dùng nó và hệ thống xác minh được toàn bộ điều kiện cần thiết. Khi đó, hệ thống vẫn có căn cứ cho phép thay vì cấp quyền chỉ vì dependency đang lỗi.

Trước khi dùng cache, cần chốt ít nhất:

| Điều kiện | Câu hỏi phải trả lời |
|---|---|
| Nguồn | Ai tạo quyết định và bằng cách nào xác minh được nguồn? |
| Phạm vi | Subject, tenant, resource, action và thuộc tính liên quan có khớp không? |
| Hiệu lực | Bắt đầu, hết hạn và phiên bản policy được hiểu thế nào? |
| Thu hồi | Mức trễ thu hồi được chấp nhận là bao nhiêu, được thực thi ra sao? |
| Toàn vẹn | Có thể sửa hoặc thay bản ghi cache để tạo ALLOW không? |
| Thời gian | Điều gì xảy ra khi không còn tin cậy phép kiểm tra thời hạn? |
| Lỗi cache | Miss, timeout, hỏng dữ liệu hoặc sai version dẫn tới trạng thái nào? |
| Điều kiện bổ sung | Có giới hạn số lần, khối lượng hoặc yêu cầu xác minh lại không? |

TTL tùy ý không thay thế phân tích thu hồi quyền. Một thời hạn phù hợp cho nội dung ít nhạy cảm có thể không phù hợp với hành động cần thu hồi nhanh.

### 8.2. Những fallback làm mất bất biến

Không được tự gia hạn quyết định hết hạn chỉ vì policy service chưa hồi phục. Không đổi khóa cache từ subject, tenant, resource, action sang chỉ subject để tăng tỷ lệ hit khi sự cố.

Nếu không chứng minh được hiệu lực theo điều kiện thời gian bắt buộc, không coi cache là ALLOW hợp lệ. Nếu một quyền ngoại tuyến có cơ chế khác, nó phải được đặc tả như một căn cứ ủy quyền riêng với phạm vi và giới hạn rõ ràng.

Tương tự, khi xác thực token, việc có payload đọc được không thay thế xác minh chữ ký, nguồn tin cậy và các điều kiện hiệu lực. Không tìm được khóa phù hợp không phải lý do bỏ bước kiểm tra. Những dữ liệu tin cậy đã cache chỉ được sử dụng nếu vẫn đáp ứng chính sách của bộ xác minh.

### 8.3. Quyền ngoại tuyến là một thiết kế, không phải một nhánh chữa cháy

Một hệ thống có thể thiết kế quyền giới hạn để hoạt động khi mất kết nối. Cần xác định trước quyền đó cho phép gì, ai phát hành, tồn tại bao lâu, ràng buộc thiết bị hoặc chủ thể thế nào và mức thu hồi trễ nào được chấp nhận.

Không đổi một quyền online thành quyền ngoại tuyến vô hạn tại thời điểm dependency lỗi. Quyết định về rủi ro phải tồn tại trong chính sách và kiến trúc trước khi trở thành hành vi runtime.

## 9. Chế độ suy giảm, circuit breaker và tính sẵn sàng

Fail closed có thể làm giảm khả năng phục vụ của hành động phụ thuộc vào cổng bảo mật. Điều đó cần được thiết kế và đo lường, thay vì che giấu bằng fallback cho phép.

Những hướng cải thiện khả năng phục vụ mà vẫn giữ ranh giới có thể gồm:

- Bố trí thành phần đánh giá quyền với khả năng chịu lỗi phù hợp.
- Đặt deadline rõ ràng cho việc thiết lập quyết định.
- Giới hạn retry và tải dồn lên dependency đang lỗi.
- Dùng căn cứ cache hoặc quyền giới hạn đã được chính sách cho phép.
- Giữ hoạt động những chức năng có căn cứ độc lập với thành phần đang lỗi.
- Thông báo trạng thái tạm không thể xác minh mà không lộ chi tiết hạ tầng.

Circuit breaker bảo vệ hệ thống khỏi tiếp tục gọi dependency lỗi. Trạng thái breaker mở không phải quyết định phân quyền. Nhánh fallback của nó vẫn phải giữ điều kiện cho phép của hành động.

Nếu request chờ quyền đã hết deadline, một kết quả ALLOW đến muộn không được kích hoạt lại thao tác đã hủy hoặc gắn sang request khác. Cần ràng buộc kết quả với đúng lần đánh giá và trạng thái của luồng.

Đối với các biện pháp như chống lạm dụng hoặc phát hiện gian lận, dự án phải xác định hành động nào được bảo vệ bởi kết quả kiểm tra. Nếu thiết kế một phương án thay thế, chẳng hạn hạn mức thấp hơn, phương án đó cần là một chính sách riêng được xác định và kiểm thử; không gọi việc bỏ toàn bộ kiểm tra là fail closed.

## 10. Tác động phụ, timeout và kết quả chưa xác định

### 10.1. Bị chặn trước hành động khác với lỗi sau hành động

Có hai tình huống cần tách riêng:

1. **Chưa thiết lập được quyền trước khi thực hiện:** không bắt đầu hành động được bảo vệ.
2. **Quyền đã hợp lệ, hành động đã gửi nhưng kết quả bị timeout:** có thể chưa biết hành động đã hoàn tất hay chưa.

Trong tình huống thứ hai, không thể dùng câu “fail closed” để khẳng định giao dịch đã được rollback. Một dependency ngoài tiến trình có thể đã nhận và thực hiện lệnh.

Yêu cầu cần chỉ rõ trạng thái chưa xác định, đối soát, idempotency và giới hạn retry. Tự gửi lại một lệnh ghi khi nhận lỗi có thể tạo tác động lặp dù cổng phân quyền ban đầu hoạt động đúng.

### 10.2. Giao dịch nội bộ không bao trùm mọi hệ thống

Rollback database không tự thu hồi email, message hoặc request thanh toán đã gửi. Nếu thiết kế có outbox, hàng đợi hoặc cơ chế bù, phải kiểm tra ý nghĩa và phạm vi của chúng đối với hành động cụ thể.

Không thực hiện trước rồi dự định “bù nếu quyền bị từ chối”. Dữ liệu đã đọc hoặc tải về không thể được thu hồi bằng một giao dịch bù.

### 10.3. Job và consumer cũng có cổng bảo mật

Một job được chấp nhận lúc người dùng còn quyền có thể bắt đầu sau khi quyền thay đổi. Cần chốt policy về thời điểm đánh giá, quyền được ủy quyền và điều kiện thực hiện lại.

Consumer không được tự dùng principal quản trị mặc định khi thiếu context của job. Principal dịch vụ hợp lệ có thể có quyền riêng, nhưng đó là một mô hình ủy quyền cần được đặc tả, không phải lý do để mọi lệnh trong queue được thực hiện.

Replay hoặc phục hồi queue phải giữ những điều kiện này. Không coi bản ghi cũ là bằng chứng đủ cho quyền hiện tại nếu hợp đồng yêu cầu xác minh lại.

## 11. Áp dụng với mã hóa, audit và phục hồi

### 11.1. Không hạ mức bảo vệ khi thiếu khóa

Nếu dữ liệu bắt buộc được mã hóa theo policy, lỗi lấy khóa không cho phép lưu hoặc gửi bản rõ. Hành động phụ thuộc cần bị giữ lại hoặc từ chối theo hợp đồng.

Một khóa cache chỉ được dùng nếu chính sách quản lý khóa cho phép và hệ thống còn xác minh được điều kiện hiệu lực liên quan. Không mặc định mọi khóa từng dùng đều có thể được dùng tiếp khi mất kết nối.

Tương tự, nếu dữ liệu tải về phải được lọc hoặc giải mã theo quyền cụ thể, lỗi của bước kiểm tra không được làm hệ thống phát hành toàn bộ dữ liệu thay thế.

### 11.2. Audit có phải là điều kiện bắt buộc?

Cần phân biệt log chẩn đoán best effort với audit được đặc tả là điều kiện của một hành động nhạy cảm.

Nếu policy yêu cầu sự kiện audit được ghi bền vững trước khi xuất dữ liệu, chỉ gọi hàm logging hoặc đẩy vào bộ nhớ chưa chứng minh điều kiện đó đã đạt. Một cơ chế spool hoặc outbox có thể đáp ứng nếu bảo đảm bền vững và quyền truy cập của nó phù hợp hợp đồng.

Nếu cả sink lẫn phương án lưu bền vững được chấp nhận đều không hoạt động, hành động phụ thuộc không được tiếp tục. Nếu audit không phải điều kiện bắt buộc của hành động, lỗi log không tự tạo ra yêu cầu dừng mọi chức năng; cần giữ đúng policy đã xác định.

Trong mọi trường hợp, thông báo và sự kiện lỗi không được phát hành secret hoặc trace thô trái phép. Lỗi logging không phải lý do chuyển dữ liệu chẩn đoán sang response công khai.

### 11.3. Phục hồi phải khôi phục điều kiện, không chỉ kết nối

Dependency trả lời lại chưa đủ để khẳng định mọi cổng có thể mở. Cần xem xét policy hiệu lực, quyền đã thu hồi, dữ liệu cache, trạng thái khóa và các job tồn đọng.

Một tiến trình phục hồi minh họa:

```text
Phát hiện thiếu điều kiện bảo mật
  -> chặn các hành động phụ thuộc, giữ chức năng có căn cứ độc lập
  -> khôi phục dependency và cấu hình
  -> xác minh nguồn quyết định, phạm vi, độ mới và trạng thái liên quan
  -> xử lý cache, job chờ và kết quả chưa xác định theo policy
  -> mở lại từng hành động sau khi đủ điều kiện
```

Health check kết nối không thay thế việc xác minh quyền. Một lần probe thành công không cho phép chuyển tất cả request đang chờ thành ALLOW.

## 12. Kiểm thử fail closed bằng fault injection

### 12.1. Quan sát kết quả và tác động thực tế

Một bộ thử cần quan sát cả:

- Response và những byte dữ liệu đã phát hành, kể cả stream.
- Lời gọi đến operation được bảo vệ.
- Thay đổi trong database và kho object.
- Message, job, outbox và request ra dependency giả lập.
- Sự kiện audit, decision ID hoặc lý do nội bộ theo policy.

Không cần dùng dữ liệu thật để chứng minh một nhánh lỗi chặn đúng. Dùng tenant, tài nguyên và dependency tổng hợp trong môi trường kiểm soát.

Một status lỗi không đủ làm oracle nếu không biết có file, message hoặc thay đổi nào đã được tạo trước đó hay không.

### 12.2. Ma trận kiểm thử minh họa

| Ca | Điều kiện kích hoạt | Điều kiện đạt |
|---|---|---|
| TC-FC-01 | ALLOW hợp lệ, đúng context | Hành động thành công trong phạm vi, chứng minh hệ thống không chặn tất cả để đạt giả |
| TC-FC-02 | DENY có căn cứ | Không có dữ liệu hoặc tác động bị cấm; không fallback sang quyền khác |
| TC-FC-03 | Policy service timeout hoặc mất kết nối | Không thực hiện hành động nếu không có căn cứ hợp lệ khác |
| TC-FC-04 | Response null, thiếu field hoặc không giải mã được | Không dùng giá trị mặc định cho phép |
| TC-FC-05 | Quyết định sai subject, tenant, resource hoặc action | Không được sử dụng cho request hiện tại |
| TC-FC-06 | Thiếu context danh tính hoặc tenant | Không thay bằng administrator hoặc phạm vi toàn cục |
| TC-FC-07 | ALLOW cache hết hạn, sai policy version hoặc không đáp ứng quy tắc thu hồi | Không tự gia hạn và không dùng bản không hợp lệ |
| TC-FC-08 | Cache hợp lệ theo policy khi dependency không sẵn sàng | Chỉ cho phép phạm vi mà căn cứ cache thực sự bao phủ |
| TC-FC-09 | Circuit breaker mở hoặc retry hết ngân sách | Không chuyển sang fallback cấp quyền |
| TC-FC-10 | Quyết định ALLOW đến sau deadline hoặc sau khi request hủy | Không khởi động lại hành động và không gắn kết quả sang request khác |
| TC-FC-11 | Không thi hành được điều kiện lọc field hoặc giới hạn số bản ghi | Không trả dữ liệu rộng hơn phạm vi được phép |
| TC-FC-12 | Audit bắt buộc không có nơi ghi bền vững | Hành động phụ thuộc bị chặn; không ghi nhận thành công giả |
| TC-FC-13 | Không thiết lập được điều kiện mã hóa bắt buộc | Không xuất hiện bản rõ ở nơi lưu, gửi hoặc fallback |
| TC-FC-14 | Quyền thay đổi trước khi job chạy, theo policy yêu cầu kiểm tra lại | Job không thực hiện bằng quyền cũ hoặc principal mặc định |
| TC-FC-15 | Dependency commit rồi response timeout | Trạng thái chưa xác định được xử lý đúng, không tự tạo lệnh lặp |
| TC-FC-16 | Phục hồi sau sự cố với cache và job cũ | Chỉ mở lại sau khi điều kiện cần được xác minh, không replay mù |

Các ca phải bám theo hợp đồng của hệ thống. Nếu chính sách cho phép một căn cứ cache cụ thể, ca timeout cần phân biệt có căn cứ đó với trường hợp không còn căn cứ nào.

### 12.3. Chứng minh đã đi qua nhánh mục tiêu

Nếu chỉ tắt một service nhưng request lại được trả từ cache hợp lệ, chưa thể kết luận đã kiểm chứng nhánh timeout không có cache. Bộ thử cần kiểm soát hoặc xác nhận trạng thái cache, breaker, retry và nguồn quyết định thực sự được dùng.

Với lỗi sau commit, phải xác nhận dependency giả lập đã commit trước khi làm mất response. Nếu request chưa tới dependency, đó là ca lỗi trước hành động, không phải kết quả chưa xác định sau hành động.

Ca đồng thời cần ràng buộc request, context và decision để phát hiện dùng nhầm quyết định. Bộ thử chỉ chạy tuần tự một tenant có thể không phát hiện khóa cache hoặc biến dùng chung sai phạm vi.

### 12.4. Tiêu chí nghiệm thu đo được

Một tiêu chí có thể là:

> Trên build và cấu hình đã ghi nhận, mọi ca bắt buộc của các hành động trong phạm vi đều được kích hoạt đúng nhánh. Không ca thiếu căn cứ cho phép nào tạo dữ liệu hoặc tác động bị cấm tại những đầu ra đã liệt kê. Các ca có căn cứ hợp lệ vẫn thành công đúng phạm vi. Phần chưa quan sát hoặc chưa kiểm chứng được ghi riêng, không tính là PASS.

Nếu có deadline hoặc giới hạn trễ thu hồi, thêm giá trị do dự án chốt và cách đo tương ứng. Không lấy một con số trong fixture làm ngưỡng mặc định cho mọi sản phẩm.

## 13. Quan sát vận hành và truy vết yêu cầu

### 13.1. Theo dõi để hiểu sự cố mà không mở quyền

Sự kiện tối thiểu có thể chứa request ID, action ID, trạng thái quyết định, mã nguyên nhân hữu hạn và revision triển khai. Không cần ghi token, secret hoặc toàn bộ object policy để giải thích rằng dependency không khả dụng.

Metric nên dùng những chiều có tập giá trị kiểm soát được, chẳng hạn loại hành động và loại lỗi. Không dùng credential hoặc request ID làm label.

Cần phân biệt số lần DENY theo policy với số lần không thiết lập được quyền. Tỷ lệ ALLOW tăng đúng lúc policy service lỗi có thể là tín hiệu cần điều tra, nhưng metric phát hiện không thay thế cổng thực thi.

### 13.2. Chuỗi truy vết minh họa

```text
R-FC-01: timeout của policy service mở đường xuất dữ liệu
  -> FC-01, FC-02, FC-05, FC-07
  -> thiết kế quyết định ba trạng thái và cổng trước export
  -> TC-FC-01, TC-FC-03, TC-FC-04, TC-FC-09, TC-FC-10
  -> response, dấu vết operation, kho object và sự kiện tổng hợp
  -> kết luận trong phạm vi build, cấu hình và nhánh đã kiểm tra
```

Một ticket triển khai cần ghi rõ hành động được bảo vệ, căn cứ cho phép, các trạng thái lỗi, chủ sở hữu cổng và những đầu ra phải quan sát. Nếu gateway, service và consumer có cổng riêng, không đóng tất cả yêu cầu chỉ vì sửa mapper ở một tầng.

Bằng chứng nên gồm cả trường hợp cho phép hợp lệ. Một bản triển khai từ chối mọi request có thể không làm lộ dữ liệu nhưng vẫn không đáp ứng hợp đồng chức năng và yêu cầu sẵn sàng.

## 14. Những cách làm dễ bị hiểu nhầm là fail closed

| Cách làm | Vấn đề | Cách đặc tả tốt hơn |
|---|---|---|
| Không nhận DENY thì cho phép | Thiếu quyết định bị coi là đủ quyền | Yêu cầu ALLOW hợp lệ một cách tường minh |
| Trả 403 sau khi đã làm nghiệp vụ | Tác động phụ hoặc dữ liệu đã ra khỏi ranh giới | Đặt cổng trước hành động, kiểm tra đầu ra thực tế |
| Tắt ghi nhưng mở mọi chức năng đọc | Đọc vẫn có thể làm lộ dữ liệu | Xác định quyền cho từng hành động |
| Dùng ALLOW cache vô thời hạn khi sự cố | Mất điều kiện hiệu lực và thu hồi | Chốt phạm vi, thời hạn và chính sách cache |
| Gateway đã kiểm tra nên backend không cần context | Backend có thể dùng sai tenant hoặc tài nguyên | Truyền context tin cậy và ràng buộc tại nơi sử dụng |
| Circuit breaker mở thì dùng default allow | Cơ chế chịu lỗi trở thành đường cấp quyền | Fallback phải giữ nguyên điều kiện bảo mật |
| Dependency hồi phục thì replay toàn bộ job | Job cũ có thể không còn quyền hoặc đã thực hiện | Kiểm tra quyền theo policy và xử lý idempotency |
| Mọi lỗi logging đều phải dừng cả hệ thống | Không phân biệt audit bắt buộc với chẩn đoán best effort | Chốt điều kiện bắt buộc cho từng hành động |
| Timeout sau thao tác ghi nghĩa là chưa xảy ra | Có thể thực hiện lặp một tác động đã commit | Biểu diễn trạng thái chưa xác định và đối soát |
| Mọi request đều bị chặn nên kiểm thử đạt | Bỏ qua chức năng và tính sẵn sàng cần thiết | Có cả ca ALLOW hợp lệ và ca suy giảm được phép |

## 15. Thực hành đặc tả cho API xuất báo cáo đa tenant

Một hệ thống cho người dùng xuất báo cáo tài chính nội bộ của tenant. API gọi policy service, tạo job, ghi audit và trả URL tải sau khi job hoàn tất. Khi policy service lỗi, code hiện dùng ALLOW gần nhất của người dùng mà không kiểm tra tenant hoặc thời hạn. Khi audit sink lỗi, job vẫn chạy. Queue có thể replay job sau khi phục hồi.

Hãy xây dựng một đặc tả gồm:

1. Bất biến bảo mật cho việc tạo job, đọc dữ liệu và cấp URL tải.
2. Mô hình ALLOW, DENY, INDETERMINATE cùng căn cứ hợp lệ cho từng hành động.
3. Danh sách context bắt buộc và cách ngăn thiếu tenant làm mở rộng truy vấn.
4. Chính sách cache gồm phạm vi, hiệu lực, thu hồi và hành vi khi không còn xác minh được điều kiện.
5. Quyết định rõ audit có phải là điều kiện bắt buộc; nếu có, định nghĩa mức bền vững được chấp nhận.
6. Cổng thực thi trước tác động phụ và thời điểm kiểm tra quyền cho job dài.
7. Hợp đồng lỗi công khai không chứa secret hoặc trace, có mã đối chiếu phù hợp.
8. Ma trận thử timeout, cache sai tenant, quyết định đến muộn, audit lỗi và queue replay.
9. Oracle xác nhận không có file, URL, message hoặc dữ liệu được phát hành trái phép.
10. Điều kiện phục hồi, chủ sở hữu và bằng chứng cần để mở lại từng hành động.

Hồ sơ cần cho người khác xác định được khi nào hệ thống có đủ căn cứ để làm việc, khi nào nó phải giữ ranh giới và chức năng nào vẫn có thể phục vụ hợp lệ trong trạng thái suy giảm.
