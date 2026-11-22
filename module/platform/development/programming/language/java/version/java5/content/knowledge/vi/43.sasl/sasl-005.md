# Phân biệt định danh xác thực và quyền đại diện trong SASL

## 1. Hai câu hỏi khác nhau khi một phiên đăng nhập

Trong SASL, một client có thể chứng minh danh tính của mình nhưng yêu cầu hoạt động dưới một danh tính khác. Vì vậy, server phải trả lời hai câu hỏi:

1. **Ai đã chứng minh danh tính?** Đây là định danh xác thực (authentication identity, thường viết `authcid` hoặc `authn ID`).
2. **Phiên này được phép hoạt động dưới danh tính nào?** Đây là định danh dùng để xét quyền (authorization identity, thường viết `authzid` hoặc `authz ID`).

Ví dụ:

```text
Dịch vụ report-bot chứng minh danh tính bằng thông tin xác thực của chính nó
        ↓
Dịch vụ yêu cầu hoạt động dưới danh tính người dùng alice
        ↓
Server kiểm tra: report-bot có được đại diện cho alice không?
        ↓
Chỉ khi được cho phép mới xác lập phiên dưới danh tính alice
```

Việc xác thực thành công `report-bot` không tự cấp quyền làm `alice`. Việc client viết `alice` vào trường yêu cầu cũng không chứng minh nó là `alice`.

SASL phân biệt hai khái niệm này ở cấp mô hình; hình thức của định danh xác thực phụ thuộc cơ chế, còn định danh dùng để xét quyền gắn với giao thức/ứng dụng. Xem [RFC 4422, Identity Concepts](https://www.rfc-editor.org/rfc/rfc4422.html#section-2).

Bài học tập trung vào mô hình và API còn áp dụng trên Java hiện đại; không cần dùng một cơ chế mật khẩu cũ để minh họa sự khác biệt.

## 2. Phân biệt yêu cầu của client với kết quả server chấp nhận

Có ba giá trị nên đặt tên tách biệt trong mã:

| Giá trị | Nguồn và ý nghĩa | Có thể dùng ngay làm danh tính phiên không? |
| --- | --- | --- |
| `authenticatedIdentity` | Danh tính gắn với bằng chứng xác thực đã được kiểm tra | Cần ánh xạ theo miền định danh của ứng dụng |
| `requestedAuthorizationIdentity` | Danh tính client đề nghị sử dụng | Không; đây là đầu vào cần kiểm tra |
| `effectiveAuthorizationIdentity` | Danh tính server đã chấp nhận sau chính sách đại diện/ánh xạ | Có, khi toàn bộ cuộc trao đổi đã hoàn tất thành công |

Hai trường hợp bình thường:

- Người dùng đăng nhập và dùng chính danh tính của mình.
- Dịch vụ được cấp quyền rõ ràng để đại diện một người dùng hoặc tài khoản khác.

Trường hợp thứ hai cần chính sách riêng. Không suy ra quyền đại diện từ việc một tài khoản là “dịch vụ nội bộ”, có tên bắt đầu bằng `svc-` hoặc có TLS hợp lệ.

Cũng không nên gộp mọi giá trị vào một biến `username`. Nếu code ghi đè tên actor ban đầu bằng tên được đại diện, phần xử lý phía sau và nhật ký sẽ mất thông tin ai đã thực sự tạo phiên.

## 3. Authzid rỗng không có nghĩa là tùy chọn bất kỳ danh tính nào

Theo khung SASL, khi chuỗi authorization identity bị bỏ qua hoặc rỗng, client yêu cầu dùng danh tính mà server liên kết với thông tin xác thực của client. Nó không có nghĩa là “không cần kiểm tra” hoặc “đăng nhập ẩn danh”.

Trong Java, tham số `authorizationId` của `Sasl.createSaslClient()` có thể là `null` hoặc chuỗi rỗng; khi đó server suy ra authorization ID từ thông tin xác thực. Xem [Sasl.createSaslClient](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/Sasl.html).

Ví dụ ánh xạ cục bộ:

```text
Bằng chứng xác thực xác lập: alice@EXAMPLE.COM
Client không yêu cầu authzid riêng
Server ánh xạ về tài khoản ứng dụng: user:alice
```

Danh tính đầu vào và đầu ra không bắt buộc giống nhau từng ký tự. Một principal có realm và một mã người dùng nội bộ có thể biểu diễn cùng thực thể ở hai miền định danh khác nhau.

Nếu client gửi authzid không rỗng, server phải hiểu đúng cú pháp/ngữ nghĩa của giao thức, ánh xạ nó về một danh tính hợp lệ và kiểm tra quyền đại diện. Cách cơ chế/provider đưa trường hợp “bỏ qua” tới callback có thể đã qua xử lý; không tự giả định callback luôn nhận chuỗi rỗng nguyên trạng từ mạng.

## 4. Quyền đại diện không phải mọi loại phân quyền

Cần tách ba bước:

```text
Xác thực bằng chứng
    ↓
Cho phép dùng danh tính yêu cầu
    ↓
Kiểm tra quyền thực hiện từng hành động nghiệp vụ
```

Ví dụ, một phiên được phép dùng danh tính `user:alice` vẫn phải kiểm tra xem `alice` có quyền đọc báo cáo cụ thể hay sửa cấu hình hệ thống không.

Nếu yêu cầu là “report-bot chỉ được đọc báo cáo thay alice”, riêng quyết định “được đại diện alice” chưa mã hóa giới hạn hành động đó. Tầng ứng dụng phải giữ ngữ cảnh actor và danh tính được đại diện, rồi kiểm tra cả hành động/tài nguyên/phạm vi cho phép.

Quyền đại diện cũng khác việc chuyển tiếp thông tin xác thực:

- Cho phép `report-bot` hoạt động dưới danh tính `alice` không đòi hỏi nó biết mật khẩu của `alice`.
- Một số cơ chế có khả năng ủy thác thông tin xác thực để dùng ở dịch vụ tiếp theo; đó là khả năng và chính sách riêng.
- Không suy ra một server được phép nhận và tái sử dụng bí mật của người dùng chỉ vì nó chấp nhận một authzid.

Một quyền đại diện cục bộ không tự lan truyền tới mọi dịch vụ phía sau. Mỗi ranh giới dịch vụ phải có cách xác thực và kiểm tra sự đại diện phù hợp với hợp đồng của nó.

## 5. AuthorizeCallback là nơi nối cơ chế với chính sách server

Với cơ chế/provider sử dụng `AuthorizeCallback`, server callback nhận hai danh tính và trả quyết định:

| API | Vai trò |
| --- | --- |
| `getAuthenticationID()` | Lấy định danh xác thực cần kiểm tra quyền đại diện |
| `getAuthorizationID()` | Lấy định danh được yêu cầu |
| `setAuthorized(boolean)` | Cho phép hoặc từ chối việc dùng danh tính đó |
| `setAuthorizedID(String)` | Cung cấp định danh kết quả đã được chuẩn hóa nếu khác giá trị được yêu cầu |
| `getAuthorizedID()` | Đọc định danh đã được cho phép của callback |

Đây là bước quyết định chính sách, không phải hàm kiểm tra mật khẩu. Trong tích hợp thật, cơ chế/provider phải cung cấp ngữ cảnh xác thực đáng tin cậy. Không lấy hai chuỗi từ request HTTP rồi tự tạo callback và xem việc callback trả `true` là đã xác thực người gửi.

Chỉ đặt `setAuthorizedID()` sau khi đã cho phép và khi cần trả một biểu diễn danh tính khác với yêu cầu ban đầu. Phương thức này không thay thế `setAuthorized(true)`. Xem [AuthorizeCallback](https://docs.oracle.com/en/java/javase/26/docs/api/java.security.sasl/javax/security/sasl/AuthorizeCallback.html).

Quy trình kiểm tra nên rõ:

1. Kiểm tra danh tính xác thực có nằm trong miền tin cậy/ánh xạ được quản lý hay không.
2. Phân giải authzid yêu cầu thành một danh tính đích hợp lệ.
3. Kiểm tra đó có phải danh tính của chính actor hay một quan hệ đại diện được cho phép.
4. Từ chối khi thiếu ánh xạ hoặc thiếu quyền.
5. Nếu cho phép, trả danh tính chuẩn hóa để toàn hệ thống dùng nhất quán.

Không viết chính sách “hai chuỗi không rỗng thì cho phép”. Cũng không chỉ kiểm tra authzid tồn tại trong cơ sở dữ liệu: sự tồn tại của `alice` không chứng minh `report-bot` có quyền đại diện cho `alice`.

## 6. Ví dụ Java: ánh xạ danh tính và quyền đại diện có giới hạn

Ví dụ sau kiểm tra riêng chính sách quyết định quyền đại diện. Nó không mở kết nối mạng, không tạo cơ chế SASL và không kiểm tra một bằng chứng mật mã.

Dữ liệu mẫu định nghĩa:

- `alice@EXAMPLE.COM` liên kết với `user:alice`.
- `report-bot@EXAMPLE.COM` liên kết với `service:report-bot`.
- Dịch vụ report-bot được đại diện `user:alice`, không được đại diện `user:bob`.
- Chuỗi `alice` là bí danh được cấu hình rõ cho `user:alice`.
- Quan hệ đại diện có hướng; không tự tạo quyền ngược lại.

Lưu thành `SaslIdentityPolicyDemo.java`:

```java
import java.util.Map;
import java.util.Set;
import javax.security.sasl.AuthorizeCallback;

public class SaslIdentityPolicyDemo {
    private static final Map<String, String> SELF = Map.of(
            "alice@EXAMPLE.COM", "user:alice",
            "report-bot@EXAMPLE.COM", "service:report-bot");

    private static final Map<String, String> TARGETS = Map.of(
            "alice", "user:alice",
            "user:alice", "user:alice",
            "bob", "user:bob",
            "user:bob", "user:bob",
            "service:report-bot", "service:report-bot");

    private static final Map<String, Set<String>> REPRESENT_AS = Map.of(
            "report-bot@EXAMPLE.COM", Set.of("user:alice"));

    static void decide(AuthorizeCallback callback) {
        String authn = callback.getAuthenticationID();
        String requested = callback.getAuthorizationID();
        if (authn == null || requested == null) {
            callback.setAuthorized(false);
            return;
        }

        String self = SELF.get(authn);
        String target = TARGETS.get(requested);
        boolean allowed = self != null && target != null
                && (target.equals(self)
                    || REPRESENT_AS.getOrDefault(authn, Set.of())
                            .contains(target));

        callback.setAuthorized(allowed);
        if (allowed && !target.equals(requested)) {
            callback.setAuthorizedID(target);
        }
    }

    static void show(String verifiedAuthn, String requested) {
        AuthorizeCallback callback =
                new AuthorizeCallback(verifiedAuthn, requested);
        decide(callback);
        String result = callback.isAuthorized()
                ? callback.getAuthorizedID() : "DENIED";
        System.out.println(verifiedAuthn + " as " + requested + " => " + result);
    }

    public static void main(String[] args) {
        show("alice@EXAMPLE.COM", "alice");
        show("report-bot@EXAMPLE.COM", "alice");
        show("report-bot@EXAMPLE.COM", "bob");
        show("alice@EXAMPLE.COM", "service:report-bot");
        show("unknown@EXAMPLE.COM", "alice");
    }
}
```

Biên dịch và chạy với JDK 17+:

```shell
javac --release 17 -encoding UTF-8 SaslIdentityPolicyDemo.java
java SaslIdentityPolicyDemo
```

Hoặc chạy tệp nguồn trực tiếp:

```shell
java SaslIdentityPolicyDemo.java
```

Kết quả:

```text
alice@EXAMPLE.COM as alice => user:alice
report-bot@EXAMPLE.COM as alice => user:alice
report-bot@EXAMPLE.COM as bob => DENIED
alice@EXAMPLE.COM as service:report-bot => DENIED
unknown@EXAMPLE.COM as alice => DENIED
```

Đọc kết quả:

- Dòng đầu là dùng chính danh tính sau ánh xạ, dù hai biểu diễn không giống nhau.
- Dòng thứ hai chỉ được chấp nhận vì bảng quyền có quan hệ report-bot → user:alice.
- Dòng thứ ba bị từ chối dù `bob` là một đích có thể phân giải.
- Dòng thứ tư chứng minh quyền đại diện không đối xứng.
- Dòng cuối từ chối actor không được ánh xạ, dù yêu cầu một tài khoản có thật.

Mẫu chỉ nhận authzid tường minh. Việc suy ra authzid khi client bỏ qua nó phải được tích hợp theo hợp đồng cơ chế/provider trước bước áp dụng chính sách tương ứng.

Các bảng `Map`/`Set` ở đây là dữ liệu kiểm chứng, không phải kho cấp quyền cho hệ thống thật. Trong ứng dụng, cần nguồn chính sách được quản lý, cập nhật và kiểm tra đúng ngữ cảnh dịch vụ. Các quyền đọc/sửa nghiệp vụ tiếp tục được kiểm tra riêng.

## 7. Chuẩn hóa tên phải giữ nguyên ranh giới tin cậy

Hai chuỗi bằng nhau không đủ để chứng minh cùng một danh tính; hai chuỗi khác nhau cũng chưa chắc là hai thực thể khác nhau. Việc ánh xạ phải dựa trên hợp đồng của cơ chế, giao thức và miền ứng dụng.

Ví dụ:

```text
alice@EXAMPLE.COM
alice@OTHER.EXAMPLE
```

Không được cắt phần realm rồi kết luận cả hai đều là `alice`. Nếu realm là một phần ranh giới tin cậy, thao tác đó có thể hợp nhất hai tài khoản khác nhau.

Tương tự:

- Không tự `toLowerCase()` cho mọi principal mà chưa biết quy tắc so sánh.
- Không `trim()` hoặc chuẩn hóa Unicode một cách tùy ý khi các tầng có quy tắc khác nhau.
- Không cho bí danh ở tenant này trỏ sang tài khoản tenant khác do thiếu điều kiện tenant.
- Không dùng tên hiển thị để thay cho mã định danh ổn định của tài khoản.
- Không để client tự chỉ định bảng ánh xạ hoặc danh sách quyền đại diện.

Trong ví dụ Java, các bí danh được liệt kê tường minh; đó là lựa chọn của chính sách mẫu. Nó không tuyên bố rằng mọi SASL mechanism đều dùng cùng cú pháp tên hoặc cùng quy tắc chuẩn hóa.

Đối với hệ thống nhiều tenant, có thể cần khóa chính sách dạng `(actor, tenant, dịch vụ đích, danh tính được đại diện)` thay vì một chuỗi username đơn lẻ.

## 8. Gắn danh tính vào phiên sau khi cuộc trao đổi hoàn tất

Chỉ chuyển sang trạng thái phiên được xác thực khi toàn bộ cuộc trao đổi đã hoàn tất thành công theo cơ chế và giao thức.

Ở phía server, sau khi `SaslServer.isComplete()` trả `true`, có thể đọc `SaslServer.getAuthorizationID()` để lấy danh tính có hiệu lực. Gọi trước khi hoàn tất là không đúng hợp đồng và có thể gây `IllegalStateException`. Xem [SaslServer.getAuthorizationID](https://docs.oracle.com/en/java/javase/21/docs/api/java.security.sasl/javax/security/sasl/SaslServer.html#getAuthorizationID()).

Nơi quản lý phiên nên giữ ít nhất các dữ liệu có ý nghĩa:

```text
authenticatedActor = report-bot@EXAMPLE.COM
effectiveIdentity = user:alice
representationDecision = allowed theo chính sách đang áp dụng
```

Đây là mô hình dữ liệu ứng dụng, không phải những thuộc tính mà mọi provider SASL đều tự trả sẵn. Ứng dụng cần thu thập thông tin qua điểm tích hợp đáng tin cậy của mình.

Không thay danh tính phiên bằng một trường như `X-User` hoặc `requestedUser` trong từng request mà bỏ qua kiểm tra đại diện mới. Nếu có tính năng chuyển danh tính sau khi đã xác thực, nó phải là một thao tác có chính sách và vòng đời riêng.

Pool kết nối cũng cần chú ý: một kết nối đã gắn danh tính không được trả lại cho người dùng khác như thể nó chưa xác thực. Cách tái xác thực hoặc dùng lại phải được giao thức và thư viện hỗ trợ rõ ràng.

## 9. Nhật ký và kiểm chứng chính sách

Một sự kiện kiểm toán nên phân biệt:

- Actor đã được xác thực.
- Danh tính được yêu cầu.
- Danh tính cuối cùng nếu được chấp nhận.
- Quyết định cho phép/từ chối và lý do phù hợp.
- Ngữ cảnh như dịch vụ, tenant, mã phiên/yêu cầu và phiên bản chính sách nếu cần.

Ví dụ sự kiện ở mức khái niệm:

```text
actor=report-bot@EXAMPLE.COM
requested=alice
effective=user:alice
decision=ALLOW
reason=explicit-representation-grant
```

Không chỉ ghi `user=alice`, vì như vậy không phân biệt được alice tự đăng nhập với report-bot đại diện alice. Không ghi mật khẩu, token hoặc toàn bộ dữ liệu phản hồi SASL để phục vụ truy vết danh tính.

Ca kiểm tra cần có:

| Ca kiểm tra | Kết quả mong đợi |
| --- | --- |
| Actor dùng chính tài khoản sau ánh xạ hợp lệ | Cho phép |
| Actor yêu cầu một tài khoản khác không có quyền | Từ chối |
| Có quyền actor A → B nhưng thử B → A | Từ chối nếu không có quyền riêng |
| Authzid tồn tại nhưng actor chưa được tin cậy/ánh xạ | Từ chối |
| Tên giống nhau ở hai realm hoặc tenant khác nhau | Không tự hợp nhất |
| Bí danh hợp lệ trỏ tới cùng mã tài khoản | Chính sách áp dụng trên danh tính chuẩn hóa |
| Quyền đại diện bị thu hồi | Không tạo phiên đại diện mới dựa trên dữ liệu quyền cũ |
| Có quyền đại diện nhưng hành động nghiệp vụ bị cấm | Từ chối hành động ở tầng nghiệp vụ |

Việc thu hồi có ảnh hưởng ngay tới phiên đang mở hay chỉ tới lần xác thực sau là quyết định vòng đời của hệ thống; cần định nghĩa rõ thay vì giả định bảng quyền đổi thì mọi phiên cũ tự thay đổi.

Bài tập:

1. Thêm quyền report-bot → user:bob vào mẫu rồi xác định dòng output nào thay đổi. Vì sao các quyền còn lại không đổi?
2. Thêm actor cùng tên ở realm khác. Hãy giữ nó là danh tính độc lập và chứng minh không được thừa hưởng quyền.
3. Thiết kế kiểm tra “chỉ đọc báo cáo” sau khi report-bot được đại diện alice. Cần thêm actor, hành động và tài nguyên vào quyết định thế nào?
4. Một người gọi gửi authzid=admin nhưng chứng minh được tài khoản thường. Bước nào phải từ chối? **Bước kiểm tra quyền dùng danh tính admin, trước khi xác lập phiên dưới danh tính đó.**
