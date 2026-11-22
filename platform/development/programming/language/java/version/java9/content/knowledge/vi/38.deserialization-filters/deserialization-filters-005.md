# Ba trạng thái ALLOWED, REJECTED và UNDECIDED

Trong một chuỗi lọc tuần tự, mỗi bộ lọc có thể đưa ra một trong ba kết quả: cho phép, từ chối hoặc không đưa ra quyết định. Ba trạng thái này tách biệt hai câu hỏi: bộ lọc có áp dụng cho yêu cầu hiện tại không, và nếu có thì kết quả chính sách là gì.

`ALLOWED` nghĩa là bộ lọc đưa ra quyết định cho phép. `REJECTED` nghĩa là bộ lọc đưa ra quyết định từ chối. `UNDECIDED` nghĩa là bộ lọc không có đủ căn cứ hoặc không chịu trách nhiệm cho trường hợp này; bộ lọc tiếp theo được quyền đánh giá.

Ba trạng thái là một mô hình quyết định do ứng dụng định nghĩa, không phải enum có sẵn trong JDK. Chúng hữu ích khi xây dựng pipeline kiểm tra quyền, quy tắc nghiệp vụ, xác thực yêu cầu hoặc chính sách nhiều lớp. Cần định nghĩa rõ cách kết hợp kết quả, vì cùng một bộ ba trạng thái có thể được dùng với nhiều thuật toán quyết định khác nhau.

## 1. Ý nghĩa chính xác của từng trạng thái

| Trạng thái | Ý nghĩa | Hành vi thường dùng trong chuỗi |
|---|---|---|
| `ALLOWED` | Bộ lọc có căn cứ và cho phép yêu cầu | Trả kết quả cho phép theo thuật toán kết hợp đã chọn |
| `REJECTED` | Bộ lọc có căn cứ và từ chối yêu cầu | Trả kết quả từ chối theo thuật toán kết hợp đã chọn |
| `UNDECIDED` | Bộ lọc không đưa ra quyết định | Tiếp tục xét bộ lọc kế tiếp |

`UNDECIDED` không có nghĩa là cho phép, cũng không có nghĩa là từ chối. Nó tương đương với việc bộ lọc abstain: bộ lọc này không quyết định trường hợp hiện tại. Bộ lọc khác hoặc chính sách mặc định sẽ quyết định kết quả cuối cùng.

Ví dụ, một bộ lọc kiểm tra danh sách chặn chỉ có trách nhiệm phát hiện các tài khoản bị khóa:

- Tài khoản bị khóa → `REJECTED`.
- Tài khoản không nằm trong danh sách khóa → `UNDECIDED`.

Kết quả thứ hai không thể được hiểu là tài khoản đã được cấp quyền. Bộ lọc này chỉ xác nhận rằng nó không có lý do để chặn; các quy tắc khác vẫn cần chạy.

Ngược lại, nếu bộ lọc chịu trách nhiệm kiểm tra một điều kiện bắt buộc và điều kiện đó không đạt, nó nên trả `REJECTED` thay vì `UNDECIDED`. Chỉ dùng `UNDECIDED` khi bộ lọc thực sự không đưa ra quyết định.

## 2. Thuật toán first-decisive: kết quả đầu tiên kết thúc chuỗi

Một cách kết hợp phổ biến là xử lý tuần tự theo thứ tự ưu tiên:

1. Chạy bộ lọc đầu tiên.
2. Nếu kết quả là `UNDECIDED`, chạy bộ lọc kế tiếp.
3. Nếu kết quả là `ALLOWED` hoặc `REJECTED`, dừng và trả kết quả đó.
4. Nếu tất cả bộ lọc đều trả `UNDECIDED`, dùng quyết định mặc định.

Đây là thuật toán first-decisive (hoặc first-applicable khi mỗi bộ lọc trả quyết định chỉ khi quy tắc của nó áp dụng). Thứ tự bộ lọc có ý nghĩa trực tiếp: bộ lọc đầu tiên đưa ra quyết định sẽ thắng.

```text
Request
  |
  v
Filter 1 -- UNDECIDED --> Filter 2
  |                         |
  | ALLOWED / REJECTED      | UNDECIDED
  v                         v
Return decision           Filter 3
                              |
                    ALLOWED / REJECTED
                              |
                              v
                        Return decision

All filters UNDECIDED
          |
          v
   Default decision
```

Với chính sách kiểm soát truy cập, nên đặt các quy tắc từ chối toàn cục như tài khoản bị khóa hoặc yêu cầu bị cấm trước các quy tắc cho phép. Nếu một bộ lọc cho phép chạy trước, chuỗi first-decisive sẽ dừng và không nhìn thấy quy tắc từ chối phía sau.

Nếu chính sách dùng mặc định từ chối, tất cả bộ lọc trả `UNDECIDED` sẽ dẫn đến `REJECTED`. Đây là cách fail-closed: thiếu quyết định cho phép thì không cấp quyền.

## 3. Không nhầm UNDECIDED với một lần kiểm tra thành công

Có ba tình huống khác nhau:

- **Quy tắc không áp dụng:** Bộ lọc không phụ trách loại yêu cầu đó → `UNDECIDED`.
- **Quy tắc áp dụng và điều kiện đạt:** Bộ lọc đã xác nhận cho phép → `ALLOWED`.
- **Quy tắc áp dụng và điều kiện không đạt:** Bộ lọc đã xác nhận từ chối → `REJECTED`.

Không nên viết một bộ lọc như sau:

```java
Decision evaluate(Request request) {
    if (request.isAdmin()) {
        return Decision.ALLOWED;
    }
    return Decision.UNDECIDED;
}
```

Đoạn code này chỉ đúng nếu bộ lọc admin không chịu trách nhiệm từ chối người không phải admin. Nếu yêu cầu nghiệp vụ là “chỉ admin được thực hiện thao tác này”, người không phải admin phải nhận `REJECTED`. Nếu còn các cơ chế cho phép khác, `UNDECIDED` có thể phù hợp hơn.

Hãy xác định trách nhiệm của từng bộ lọc trước khi chọn trạng thái. Nếu không, một bộ lọc có thể vô tình biến một điều kiện bắt buộc thành điều kiện tùy chọn.

## 4. Ví dụ Java 17: chuỗi quyết định theo thứ tự

Ví dụ dưới đây mô phỏng chính sách gồm ba quy tắc:

1. Tài khoản bị khóa luôn bị từ chối.
2. Client đáng tin cậy được cho phép.
3. Vai trò admin được cho phép.
4. Nếu không quy tắc nào quyết định, mặc định từ chối.

Bộ lọc không áp dụng trả `UNDECIDED`. Bộ lọc có quyết định trả `ALLOWED` hoặc `REJECTED` và kết thúc chuỗi. Các thuộc tính trong record chỉ là dữ liệu test; trong ứng dụng thật, trạng thái tài khoản và danh tính phải đến từ nguồn xác thực phía server, không tin boolean do client tự gửi.

**Main.java**

```java
import java.util.List;
import java.util.Objects;

public class Main {
    enum Decision {
        ALLOWED,
        REJECTED,
        UNDECIDED
    }

    record Request(
            String name,
            boolean blocked,
            boolean trusted,
            boolean admin) {
    }

    @FunctionalInterface
    interface DecisionFilter {
        Decision evaluate(Request request);
    }

    record NamedFilter(String name, DecisionFilter filter) {
    }

    record Evaluation(
            Decision decision,
            String source,
            List<String> trace) {
    }

    static Evaluation evaluate(
            Request request,
            List<NamedFilter> filters) {

        var trace = new java.util.ArrayList<String>();

        for (NamedFilter filter : filters) {
            Decision decision = Objects.requireNonNull(
                    filter.filter().evaluate(request),
                    "Filter returned null: " + filter.name());

            trace.add(filter.name() + "=" + decision);

            if (decision != Decision.UNDECIDED) {
                return new Evaluation(
                        decision,
                        filter.name(),
                        List.copyOf(trace));
            }
        }

        trace.add("default=REJECTED");
        return new Evaluation(
                Decision.REJECTED,
                "default",
                List.copyOf(trace));
    }

    public static void main(String[] args) {
        List<NamedFilter> filters = List.of(
                new NamedFilter(
                        "blocklist",
                        request -> request.blocked()
                                ? Decision.REJECTED
                                : Decision.UNDECIDED),
                new NamedFilter(
                        "trusted-client",
                        request -> request.trusted()
                                ? Decision.ALLOWED
                                : Decision.UNDECIDED),
                new NamedFilter(
                        "admin-role",
                        request -> request.admin()
                                ? Decision.ALLOWED
                                : Decision.UNDECIDED)
        );

        List<Request> requests = List.of(
                new Request("blocked-trusted", true, true, false),
                new Request("trusted", false, true, false),
                new Request("admin", false, false, true),
                new Request("guest", false, false, false)
        );

        for (Request request : requests) {
            Evaluation result = evaluate(request, filters);

            System.out.println(
                    request.name() + ": "
                    + String.join(" -> ", result.trace())
                    + " => " + result.decision()
                    + " (by " + result.source() + ")");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -Xlint:all Main.java
java Main
```

Kết quả stdout:

```text
blocked-trusted: blocklist=REJECTED => REJECTED (by blocklist)
trusted: blocklist=UNDECIDED -> trusted-client=ALLOWED => ALLOWED (by trusted-client)
admin: blocklist=UNDECIDED -> trusted-client=UNDECIDED -> admin-role=ALLOWED => ALLOWED (by admin-role)
guest: blocklist=UNDECIDED -> trusted-client=UNDECIDED -> admin-role=UNDECIDED -> default=REJECTED => REJECTED (by default)
```

Quan sát từng trường hợp:

- `blocked-trusted` bị từ chối ngay ở bộ lọc đầu tiên. Việc client đáng tin cậy không thể vượt qua quy tắc chặn có độ ưu tiên cao hơn.
- `trusted` được cho phép ở bộ lọc thứ hai. Bộ lọc admin không cần chạy.
- `admin` đi qua hai bộ lọc đầu với trạng thái `UNDECIDED` và được bộ lọc thứ ba cho phép.
- `guest` không được bộ lọc nào quyết định. Chính sách mặc định từ chối.

Danh sách `trace` giúp biết bộ lọc nào đã chạy và bộ lọc nào đưa ra quyết định. Trong production, có thể ghi trace ở mức DEBUG để chẩn đoán chính sách; tránh ghi dữ liệu nhạy cảm của request vào log.

## 5. Thứ tự bộ lọc và chính sách kết hợp

First-decisive là một lựa chọn, không phải quy tắc bắt buộc cho mọi hệ thống ba trạng thái. Cần chọn thuật toán kết hợp phù hợp với ý nghĩa của các bộ lọc.

| Thuật toán | Cách kết hợp | Khi phù hợp |
|---|---|---|
| First-decisive | Quyết định đầu tiên khác UNDECIDED kết thúc chuỗi | Quy tắc có thứ tự ưu tiên rõ ràng |
| Deny-overrides | Bất kỳ REJECTED nào cũng thắng; nếu không có REJECTED và có ALLOWED thì cho phép | Mọi quy tắc từ chối đều phải được tôn trọng |
| Allow-overrides | Bất kỳ ALLOWED nào cũng thắng; nếu không có ALLOWED và có REJECTED thì từ chối | Một nguồn cho phép đủ để cấp quyền theo chính sách |
| Unanimous | Có REJECTED thì từ chối; chỉ cho phép khi có ít nhất một ALLOWED và không có REJECTED/UNDECIDED chưa xử lý theo quy tắc | Nhiều bên phải đồng thuận |

Với deny-overrides, không thể dừng ngay khi gặp `ALLOWED`, vì một bộ lọc phía sau vẫn có thể trả `REJECTED`. Có thể dừng ngay khi gặp `REJECTED` nếu chính sách đã xác định rằng một lần từ chối là đủ.

Với first-decisive, cả `ALLOWED` và `REJECTED` đều kết thúc chuỗi. Với deny-overrides, `ALLOWED` chỉ là một phiếu cho phép và cần tiếp tục kiểm tra các bộ lọc còn lại. Không trộn hai cách này trong cùng pipeline nếu chưa xác định rõ quy tắc.

## 6. Chọn quyết định mặc định

Nếu toàn bộ bộ lọc trả `UNDECIDED`, hệ thống phải có quyết định cuối cùng. Không để trạng thái này tự chuyển thành cho phép một cách ngầm định.

| Mặc định | Hành vi | Lưu ý |
|---|---|---|
| `REJECTED` | Không có quy tắc cho phép thì từ chối | Phù hợp với authorization và allowlist |
| `ALLOWED` | Không có quy tắc từ chối thì cho phép | Chỉ phù hợp khi nghiệp vụ xác định rõ open-by-default |
| Trả trạng thái chưa quyết định | Giao cho tầng gọi xử lý tiếp | Chỉ dùng khi hợp đồng API yêu cầu tầng khác quyết định |

Đối với quyền truy cập, mặc định từ chối thường an toàn hơn. Khi có lỗi cấu hình, thiếu bộ lọc hoặc request không khớp quy tắc nào, hệ thống không vô tình cấp quyền.

Không phải mọi pipeline đều là authorization. Với bộ lọc định tuyến hoặc phân loại, kết quả cuối có thể là “không có bộ xử lý phù hợp” thay vì REJECTED. Hãy biểu diễn rõ trường hợp đó bằng kiểu kết quả hoặc lỗi nghiệp vụ riêng, không gán nhầm ý nghĩa bảo mật.

## 7. Tổ chức bộ lọc để dễ bảo trì

Mỗi bộ lọc nên có một trách nhiệm nhỏ và có thể kiểm thử độc lập:

- Kiểm tra trạng thái tài khoản.
- Kiểm tra loại yêu cầu hoặc phạm vi tài nguyên.
- Kiểm tra vai trò hoặc quyền.
- Kiểm tra giới hạn theo thời gian hoặc quota.
- Áp dụng chính sách mặc định ở cuối chuỗi.

Tên bộ lọc nên thể hiện điều kiện mà nó quyết định. Tránh một bộ lọc lớn vừa xác thực danh tính, vừa kiểm tra quota, vừa quyết định quyền và vừa ghi log.

Các quy tắc nên được cấu hình hoặc sắp xếp tại một nơi. Không để mỗi bộ lọc tự thêm một bộ lọc khác vào chuỗi khi đang đánh giá request, vì điều đó làm thứ tự và kết quả khó dự đoán.

Nếu danh sách bộ lọc có thể thay đổi trong runtime, hãy tạo một snapshot bất biến cho mỗi lần đánh giá. Điều này giúp một request không chạy trên một nửa cấu hình cũ và một nửa cấu hình mới.

## 8. Xử lý lỗi trong bộ lọc

Một exception trong bộ lọc không tự động tương đương với `UNDECIDED`. Hai trạng thái có ý nghĩa khác nhau:

- `UNDECIDED` là kết quả nghiệp vụ hợp lệ: bộ lọc không quyết định.
- Exception là lỗi kỹ thuật hoặc lỗi thực thi: bộ lọc không thể hoàn tất đánh giá theo hợp đồng.

Không nên bắt mọi exception rồi trả `UNDECIDED`. Làm như vậy có thể khiến lỗi truy cập database, lỗi xác thực hoặc lỗi cấu hình bị hiểu thành “bộ lọc này không quan tâm”, rồi một bộ lọc cho phép phía sau cấp quyền.

Chọn chính sách lỗi rõ ràng:

1. Với kiểm soát truy cập, lỗi của bộ lọc bắt buộc thường phải fail-closed, trả lỗi hoặc từ chối theo hợp đồng.
2. Với bộ lọc tùy chọn, chỉ trả `UNDECIDED` khi dữ liệu hợp lệ cho thấy bộ lọc không áp dụng.
3. Ghi log lỗi ở tầng có đủ ngữ cảnh, không ghi token hoặc dữ liệu bí mật.
4. Không để exception bị bỏ qua âm thầm.

## 9. Phân biệt với các API lọc có sẵn trong Java

Không nhầm mô hình ba trạng thái này với mọi API có tên filter trong JDK:

- `java.util.function.Predicate<T>` trả về boolean: true hoặc false. Nó không có trạng thái UNDECIDED.
- `Stream.filter(predicate)` giữ lại phần tử khi predicate trả true và loại phần tử khi trả false. Nó không triển khai một chính sách ba trạng thái.
- `java.util.logging.Filter` dùng `isLoggable(LogRecord)` trả boolean để quyết định log record có được ghi hay không.
- `System.Logger` và JUL level điều khiển mức logging, không phải kết quả authorization ba trạng thái.

Nếu ứng dụng cần ba trạng thái, hãy định nghĩa enum và interface phù hợp với domain như ví dụ. Không ép `UNDECIDED` vào boolean bằng cách mặc định true; điều đó có thể biến một bộ lọc không áp dụng thành bộ lọc cho phép.

## 10. Kiểm thử các nhánh và thứ tự

Bộ kiểm thử nên bao phủ tối thiểu:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Bộ lọc đầu tiên từ chối | REJECTED; bộ lọc sau không chạy |
| Bộ lọc đầu tiên undecided, bộ lọc sau cho phép | ALLOWED |
| Nhiều bộ lọc undecided, bộ lọc sau cùng cho phép | ALLOWED |
| Tất cả bộ lọc undecided | Áp dụng default decision |
| Bộ lọc từ chối đứng sau bộ lọc cho phép trong first-decisive | Bộ lọc từ chối không chạy |
| Bộ lọc trả null | Báo lỗi hợp đồng, không coi là UNDECIDED |
| Bộ lọc ném exception | Áp dụng chính sách lỗi đã định nghĩa |

Kiểm thử thứ tự đặc biệt quan trọng. Chỉ kiểm thử từng bộ lọc riêng lẻ không chứng minh pipeline kết hợp đúng. Cần có test xác nhận short-circuit, bộ lọc không chạy sau quyết định cuối và mặc định khi không có quyết định.

## 11. Lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Coi UNDECIDED là ALLOWED | Yêu cầu không được kiểm tra vẫn được cấp quyền | Chỉ ALLOWED mới là quyết định cho phép |
| Coi UNDECIDED là REJECTED ngay tại mỗi bộ lọc | Chuỗi không thể chuyển sang bộ lọc khác | Tiếp tục khi bộ lọc abstain |
| Không có default decision | Kết quả cuối không xác định | Khai báo rõ mặc định |
| Đặt allow trước global deny trong first-decisive | Quy tắc cho phép có thể che quy tắc từ chối | Đặt deny ưu tiên trước hoặc chọn deny-overrides |
| Trộn first-decisive với deny-overrides | Hành vi thay đổi tùy vị trí bộ lọc | Chọn một thuật toán kết hợp rõ ràng |
| Bắt exception và trả UNDECIDED | Lỗi kỹ thuật bị che giấu, có thể mở đường cho allow | Phân biệt lỗi thực thi với abstain |
| Trả null | Caller không biết đó là lỗi hay trạng thái thứ tư | Bắt buộc trả một trong ba enum value |
| Bộ lọc có side effect khó lặp lại | Kết quả khó kiểm thử và khó tái sử dụng | Giữ bước đánh giá thuần; thực hiện side effect sau quyết định |

## 12. Checklist thiết kế

- Enum có đúng ba trạng thái và tên trạng thái phản ánh đúng nghiệp vụ không?
- Mỗi bộ lọc có định nghĩa rõ khi nào trả ALLOWED, REJECTED và UNDECIDED không?
- UNDECIDED có thật sự là “không quyết định” thay vì “điều kiện đạt” không?
- Thuật toán kết hợp là first-decisive, deny-overrides hay một chính sách khác?
- Thứ tự ưu tiên của các bộ lọc có được xác định và kiểm thử không?
- Quyết định mặc định khi mọi bộ lọc đều undecided đã rõ chưa?
- Exception và null có được xử lý riêng, không biến thành UNDECIDED không?
- Có trace hoặc log đủ để giải thích vì sao request được cho phép hoặc từ chối không?
- Các thông tin danh tính/quyền có đến từ nguồn tin cậy phía server không?
- Có test cho short-circuit, default decision, thứ tự và lỗi bộ lọc không?

Ba trạng thái ALLOWED, REJECTED và UNDECIDED giúp chuỗi lọc biểu diễn rõ sự khác nhau giữa quyết định và việc không đưa ra quyết định. Trong chính sách first-decisive, UNDECIDED chuyển quyền đánh giá cho bộ lọc kế tiếp; ALLOWED hoặc REJECTED kết thúc chuỗi; nếu không bộ lọc nào quyết định thì áp dụng mặc định. Hãy chọn thuật toán kết hợp, thứ tự ưu tiên và default decision trước khi triển khai để tránh vô tình cho phép yêu cầu chưa được kiểm tra.
