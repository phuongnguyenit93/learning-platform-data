# Chống bấm liên tục và xử lý phản hồi đến khác thứ tự

Trong một màn hình Spring Web Flow, người dùng có thể nhấn nút nhiều lần trước khi request đầu tiên hoàn tất. Với giao diện AJAX, người dùng cũng có thể gửi nhiều yêu cầu đọc dữ liệu và nhận phản hồi theo thứ tự khác với thứ tự gửi. Nếu mỗi phản hồi đều cập nhật giao diện, dữ liệu cũ có thể ghi đè dữ liệu mới. Nếu nhiều POST cùng tác động lên một flow execution, ứng dụng còn có nguy cơ xử lý lặp một hành động nghiệp vụ hoặc nhận request dựa trên trạng thái flow đã thay đổi.

Bài này thuộc chương **Ajax và phân mảnh** của module **SPRING_WEB_FLOW**. Trọng tâm là phối hợp kiểm soát thao tác ở trình duyệt, xử lý request tại máy chủ và cập nhật fragment đúng thứ tự. Mục tiêu là bảo vệ hành trình nhiều bước dùng state, event và transition, đồng thời giữ giao diện nhất quán khi mạng chậm, người dùng nhấn liên tục hoặc nhiều phản hồi trở về không theo thứ tự.

## Kết quả cần đạt

Sau bài này, bạn có thể:

- Ngăn một biểu mẫu gửi lặp cùng một thao tác khi request trước vẫn đang xử lý.
- Phân biệt chống nhấn lặp ở trình duyệt với idempotency ở tầng nghiệp vụ.
- Bỏ qua phản hồi cũ của các request đọc dữ liệu khi đã có request mới hơn.
- Tuần tự hóa các lệnh AJAX làm thay đổi flow state hoặc dữ liệu nghiệp vụ.
- Giữ execution URL, event ID và token bảo vệ request đúng với flow hiện tại.
- Hiển thị trạng thái đang xử lý, lỗi mạng và khả năng thử lại.
- Kiểm thử nhấn đúp, phản hồi đảo thứ tự, retry và request đồng thời.

## 1. Vì sao thao tác lặp và phản hồi đảo thứ tự gây lỗi?

Giả sử màn hình rà soát đơn hàng có nút **Xác nhận**. Người dùng nhấn hai lần vì trang chưa phản hồi. Trình duyệt gửi hai POST cùng event. Nếu cả hai request đều được xử lý như hai ý định xác nhận độc lập, hệ thống có thể ghi nhận hai giao dịch hoặc request thứ hai gặp lỗi vì flow execution đã chuyển state sau request thứ nhất.

Một tình huống khác xảy ra khi giao diện tải các phần dữ liệu độc lập. Người dùng đổi bộ lọc từ **Tất cả** sang **Đang chờ** rồi nhanh chóng chọn **Đã xử lý**. Request thứ hai có thể hoàn tất trước request thứ nhất. Nếu phản hồi cũ đến sau và vẫn cập nhật vùng kết quả, giao diện quay lại hiển thị dữ liệu của bộ lọc **Tất cả** dù lựa chọn hiện tại là **Đã xử lý**.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Trình duyệt
    participant S as Máy chủ

    U->>B: Chọn bộ lọc A
    B->>S: GET dữ liệu A
    U->>B: Chọn bộ lọc B
    B->>S: GET dữ liệu B
    S-->>B: Phản hồi B (đến trước)
    B->>B: Hiển thị dữ liệu B
    S-->>B: Phản hồi A (đến sau)
    B->>B: Nếu không kiểm tra phiên bản, A ghi đè B
~~~

Hai vấn đề cần giải quyết riêng:

- **Thao tác lặp** là nhiều request cùng biểu diễn một ý định hoặc một command. Cần chặn thao tác dư ở giao diện và bảo vệ tính đúng đắn ở máy chủ.
- **Phản hồi đảo thứ tự** là response của request cũ đến sau response mới. Với dữ liệu chỉ dùng để hiển thị, có thể bỏ qua response cũ. Với command làm thay đổi trạng thái, cần kiểm soát thứ tự thực thi và kết quả nghiệp vụ ở máy chủ.

Chỉ vô hiệu hóa nút sau lần nhấn đầu không đủ để bảo vệ dữ liệu. Request có thể được gửi từ tab khác, thiết bị khác, script hoặc được gửi lại sau lỗi mạng. Ngược lại, chỉ dùng idempotency ở máy chủ không ngăn giao diện nhấp nháy hoặc hiển thị fragment cũ.

## 2. Chặn gửi lặp tại biểu mẫu

Với một form chỉ cho phép một lần submit tại một thời điểm, hãy đặt cờ đang gửi trước khi bắt đầu request và vô hiệu hóa các nút submit. Cờ phải được đặt đồng bộ ngay trong handler để lần nhấn tiếp theo bị chặn trước khi request đầu tiên hoàn tất.

Ví dụ HTML:

~~~html
<form id="checkout-form"
      method="post"
      action="${flowExecutionUrl}">

    <button type="submit"
            name="_eventId_confirm"
            value="confirm">
        Xác nhận
    </button>
</form>

<div id="checkout-status" aria-live="polite"></div>
<div id="checkout-result"></div>
~~~

Ví dụ JavaScript minh họa một request tại một thời điểm:

~~~javascript
const form = document.querySelector("#checkout-form");
const statusRegion = document.querySelector("#checkout-status");

let submitting = false;

form.addEventListener("submit", async function (event) {
    event.preventDefault();

    if (submitting) {
        return;
    }

    submitting = true;

    const submitter = event.submitter;
    const buttons = Array.from(
        form.querySelectorAll("button[type=submit], input[type=submit]")
    );
    const previousDisabled = buttons.map(function (button) {
        return button.disabled;
    });

    try {
        const data = new FormData(form, submitter);

        buttons.forEach(function (button) {
            button.disabled = true;
        });

        form.setAttribute("aria-busy", "true");
        statusRegion.textContent = "Đang xử lý yêu cầu...";

        const response = await fetch(form.action, {
            method: "POST",
            body: data,
            headers: {
                "X-Requested-With": "XMLHttpRequest"
            }
        });

        if (!response.ok) {
            throw new Error("HTTP " + response.status);
        }

        if (response.redirected) {
            window.location.assign(response.url);
            return;
        }

        const html = await response.text();

        // Chỉ dùng vùng fragment nếu endpoint được thiết kế
        // để trả về HTML fragment tương ứng.
        statusRegion.textContent = "Yêu cầu đã được xử lý.";
        document.querySelector("#checkout-result").innerHTML = html;
    } catch (error) {
        statusRegion.textContent =
            "Chưa xác nhận được kết quả. Hãy kiểm tra trạng thái trước khi thử lại.";
    } finally {
        submitting = false;
        form.removeAttribute("aria-busy");

        buttons.forEach(function (button, index) {
            button.disabled = previousDisabled[index];
        });
    }
});
~~~

Cờ **submitting** được đặt trước lệnh **fetch**, vì vậy các submit tiếp theo bị chặn ngay cả khi trình duyệt chưa nhận response. Thuộc tính **aria-busy** và vùng **aria-live** giúp công nghệ hỗ trợ thông báo rằng biểu mẫu đang xử lý.

Ví dụ dùng **FormData(form, submitter)** để giữ cả tên và giá trị của nút submit được nhấn, ví dụ **_eventId_confirm**. Nếu cần hỗ trợ trình duyệt không có overload này, hãy thêm tên/giá trị submitter vào FormData theo cách tương thích. Nếu không gửi event ID, FlowHandlerAdapter có thể không nhận được event mà transition mong đợi.

Mẫu trên giả định endpoint trả về HTML fragment. Nếu cấu hình Spring Web Flow của ứng dụng sử dụng POST–Redirect–GET để điều hướng toàn trang, hãy để trình duyệt theo redirect hoặc dùng form submit thông thường. Không chèn response của một trang hoàn chỉnh vào một vùng fragment. Cơ chế AJAX và định dạng response phải được thống nhất ở phía view/handler của ứng dụng.

## 3. Phân biệt khóa nút và idempotency phía máy chủ

Khóa nút là biện pháp cải thiện trải nghiệm. Nó chỉ kiểm soát một giao diện trong một tab trình duyệt. Máy chủ vẫn cần bảo vệ command có side effect khỏi việc được thực hiện nhiều lần.

Một cách phổ biến là cấp **idempotency key** cho mỗi ý định nghiệp vụ. Ví dụ, khi người dùng bắt đầu xác nhận đơn hàng, máy chủ cấp một mã command duy nhất và form gửi mã đó cùng request. Nếu cùng một command được gửi lại do nhấn đúp, retry hoặc mạng mất response, dịch vụ nhận ra key đã xử lý và trả lại kết quả đã lưu thay vì tạo giao dịch mới.

Luồng xử lý:

~~~mermaid
flowchart TD
    A[Người dùng xác nhận] --> B[Form gửi command ID]
    B --> C[Service kiểm tra idempotency key]
    C --> D{Key đã được xử lý?}
    D -->|Có| E[Trả lại kết quả đã lưu]
    D -->|Chưa| F[Kiểm tra quyền và trạng thái nghiệp vụ]
    F --> G[Thực hiện giao dịch]
    G --> H[Lưu kết quả cùng key trong transaction]
    H --> I[Trả kết quả]
~~~

Ví dụ dữ liệu command:

~~~java
public class ConfirmOrderCommand {
    private String orderId;
    private String idempotencyKey;

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }

    public String getIdempotencyKey() {
        return idempotencyKey;
    }

    public void setIdempotencyKey(String idempotencyKey) {
        this.idempotencyKey = idempotencyKey;
    }
}
~~~

Service cần kiểm tra key theo phạm vi phù hợp, thường gắn với người dùng/tenant và loại thao tác. Cơ sở dữ liệu nên có ràng buộc duy nhất để hai request đến đồng thời không cùng vượt qua bước kiểm tra rồi ghi hai kết quả. Việc lưu key, kết quả và thay đổi nghiệp vụ nên nằm trong một transaction hoặc một cơ chế bảo đảm nhất quán tương đương.

Không dùng execution key của Spring Web Flow làm idempotency key. Một flow execution có thể chứa nhiều command hợp lệ khác nhau như lưu bản nháp, xác nhận và hủy. Idempotency key đại diện cho một ý định cụ thể và cần được tái sử dụng khi retry đúng ý định đó; một command mới phải có key mới.

Nếu mạng bị ngắt sau khi máy chủ đã commit nhưng trước khi trình duyệt nhận response, giao diện không thể kết luận thao tác thất bại. Hãy truy vấn trạng thái command hoặc gửi lại cùng idempotency key. Không tạo key mới ngay khi retry, vì như vậy máy chủ có thể coi đó là một giao dịch mới.

## 4. Bỏ qua response cũ cho vùng dữ liệu chỉ đọc

Với request đọc dữ liệu như tải danh sách, gợi ý hoặc nội dung xem trước, có thể dùng số thứ tự request. Mỗi lần người dùng thay đổi lựa chọn, tăng số thứ tự. Khi response trở về, chỉ cập nhật giao diện nếu số thứ tự của response vẫn là số mới nhất.

~~~javascript
const resultsRegion = document.querySelector("#search-results");
let latestSearchVersion = 0;

async function refreshResults(query) {
    const requestVersion = ++latestSearchVersion;

    try {
        const response = await fetch(
            "/search/fragment?q=" + encodeURIComponent(query),
            {
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                }
            }
        );

        if (!response.ok) {
            throw new Error("HTTP " + response.status);
        }

        const html = await response.text();

        // Bỏ qua response nếu một lần tìm kiếm mới hơn đã bắt đầu.
        if (requestVersion !== latestSearchVersion) {
            return;
        }

        resultsRegion.innerHTML = html;
    } catch (error) {
        if (requestVersion === latestSearchVersion) {
            resultsRegion.textContent = "Không thể tải kết quả.";
        }
    }
}
~~~

Ví dụ, request tìm kiếm **A** có version 1 và request **B** có version 2. Nếu response B đến trước, nó được hiển thị. Khi response A đến sau, điều kiện version không còn đúng nên A bị bỏ qua.

Cách này thường được gọi là **latest response wins**. Nó phù hợp với dữ liệu chỉ đọc mà lựa chọn mới nhất của người dùng thay thế lựa chọn trước. Nó không phù hợp để quyết định command nào được thực thi hoặc command nào đã commit.

Chỉ chèn HTML fragment do máy chủ tạo và đã escape dữ liệu không tin cậy. Nếu endpoint trả văn bản thuần, dùng **textContent** thay vì **innerHTML**. Không đưa trực tiếp chuỗi do người dùng nhập vào HTML fragment mà không mã hóa đầu ra phù hợp.

## 5. Hủy request cũ bằng AbortController

Với request đọc dữ liệu, có thể hủy request trước khi gửi request mới để giảm tải mạng và tránh xử lý response không còn cần thiết:

~~~javascript
let currentController = null;
let currentVersion = 0;

async function loadPreview(itemId) {
    currentVersion += 1;
    const version = currentVersion;

    if (currentController) {
        currentController.abort();
    }

    const controller = new AbortController();
    currentController = controller;

    try {
        const response = await fetch(
            "/preview/" + encodeURIComponent(itemId),
            {
                signal: controller.signal,
                headers: {
                    "X-Requested-With": "XMLHttpRequest"
                }
            }
        );

        if (!response.ok) {
            throw new Error("HTTP " + response.status);
        }

        const html = await response.text();

        if (version !== currentVersion) {
            return;
        }

        document.querySelector("#preview").innerHTML = html;
    } catch (error) {
        if (error.name !== "AbortError" && version === currentVersion) {
            document.querySelector("#preview").textContent =
                "Không thể tải bản xem trước.";
        }
    }
}
~~~

**AbortController** giúp trình duyệt ngừng chờ hoặc hủy request ở phía client. Tuy nhiên, hủy fetch không bảo đảm máy chủ chưa nhận request hoặc đã dừng xử lý. Nếu request đã đến server và action nghiệp vụ đã chạy, abort phía trình duyệt không thể rollback giao dịch. Vì vậy, chỉ nên dùng hủy request như tối ưu cho thao tác đọc hoặc tính toán không có side effect; command ghi dữ liệu vẫn cần idempotency và kiểm soát ở máy chủ.

Kết hợp version check với abort giúp xử lý cả trường hợp request cũ không hủy kịp nhưng response vẫn đến sau. Version check là điều kiện quyết định response nào được cập nhật giao diện.

## 6. Tuần tự hóa các event làm thay đổi flow state

Các event như **continue**, **confirm**, **cancel** hoặc **save** có thể làm thay đổi state, dữ liệu trong flow scope và trạng thái nghiệp vụ. Không nên gửi song song nhiều event trên cùng flow execution rồi chỉ dựa vào thứ tự response để quyết định giao diện.

Ví dụ, request **confirm** có thể làm flow chuyển từ state **review** sang **completed**. Một request **back** gửi gần như đồng thời vẫn có thể mang execution key hoặc giả định state cũ. Kết quả phụ thuộc request nào được xử lý trước và cách repository/flow execution lock của ứng dụng điều phối truy cập đồng thời.

Với một vùng điều khiển flow, hãy cho phép một command đang chạy tại một thời điểm. Sau khi nhận kết quả, cập nhật view hoặc chuyển trang; chỉ khi flow đang ở state hợp lệ mới bật thao tác tiếp theo. Nếu có nhiều loại command cần chạy đồng thời, hãy tách chúng theo tài nguyên/flow execution độc lập và xác định thứ tự ở tầng nghiệp vụ.

Các quy tắc thực hành:

- Mỗi flow execution chỉ có một event thay đổi state đang được gửi từ một giao diện tại một thời điểm.
- Sau khi gửi event, tạm khóa các nút điều hướng có thể phát event xung đột.
- Khi response là redirect, điều hướng theo URL trả về hoặc để trình duyệt xử lý theo PRG.
- Nếu response là fragment, chỉ thay vùng được chỉ định sau khi xác nhận request vẫn là thao tác hiện hành.
- Khi nhận lỗi stale execution hoặc state không hợp lệ, tải lại trạng thái flow theo đường phục hồi; không tự gửi lại event bằng execution key cũ.
- Với command nghiệp vụ có thể bị gửi lại, dùng idempotency key ở service và ràng buộc dữ liệu.

Repository hoặc cơ chế khóa của Spring Web Flow có thể bảo vệ việc truy cập đồng thời vào execution theo cấu hình triển khai. Dù vậy, cơ chế đó không quyết định fragment nào còn phù hợp với lựa chọn mới nhất của người dùng và không thay thế idempotency cho side effect. Hãy kiểm tra repository/locking strategy thực tế và vẫn kiểm soát giao diện cũng như nghiệp vụ ở các lớp tương ứng.

## 7. Xử lý response lỗi và trạng thái không xác định

Không phải response nào cũng là fragment thành công. Một request AJAX có thể nhận 401/403, 409, 5xx hoặc trang đăng nhập do session hết hạn. Nếu ứng dụng luôn đưa response vào vùng HTML, người dùng có thể nhìn thấy trang lỗi hoặc trang đăng nhập bên trong một phần nhỏ của màn hình.

Nên xác định hợp đồng response rõ ràng:

| Kết quả | Cách xử lý phía giao diện |
|---|---|
| 2xx với fragment hợp lệ | Kiểm tra request còn mới nhất rồi thay vùng fragment. |
| 3xx điều hướng toàn trang | Thực hiện navigation theo URL đích nếu endpoint được thiết kế để redirect; không chèn HTML toàn trang vào fragment. |
| 401 Unauthorized | Yêu cầu đăng nhập lại hoặc điều hướng đến trang đăng nhập. |
| 403 Forbidden | Hiển thị thông báo quyền truy cập/CSRF phù hợp; không tự retry vô hạn. |
| 409 Conflict | Tải lại trạng thái nghiệp vụ hoặc thông báo rằng dữ liệu đã thay đổi. |
| 5xx hoặc lỗi mạng | Giữ trạng thái đã biết, cho phép kiểm tra lại kết quả trước khi retry command. |

Đặc biệt với thao tác xác nhận, timeout không có nghĩa là thất bại. Máy chủ có thể đã commit giao dịch nhưng response không đến được trình duyệt. Hãy dùng idempotency key để truy vấn hoặc gửi lại cùng command. Giao diện nên thể hiện trạng thái **Đang xác minh kết quả** thay vì ngay lập tức cho phép tạo một giao dịch mới.

Nếu response bị bỏ qua vì đã cũ, không cần hiển thị lỗi cho người dùng. Nếu response mới nhất thất bại, hiển thị thông báo tại đúng vùng đang hoạt động và giữ dữ liệu người dùng đã nhập khi có thể.

## 8. Kiểm thử nhấn lặp và response đến khác thứ tự

Kiểm thử nên mô phỏng độ trễ mạng thay đổi, vì race condition thường không xuất hiện khi mọi request đều hoàn tất nhanh và theo thứ tự.

| Kịch bản | Điều cần xác nhận |
|---|---|
| Nhấn submit hai lần liên tiếp | Chỉ một request được gửi từ cùng form trong khi request đầu đang xử lý. |
| Hai request cùng idempotency key đến đồng thời | Chỉ một side effect được ghi nhận; request còn lại nhận kết quả đã lưu. |
| Request đọc A gửi trước B nhưng response B đến trước | Fragment B được hiển thị; response A bị bỏ qua. |
| Abort request A rồi gửi B | A không cập nhật giao diện kể cả khi response vẫn đến; B được hiển thị nếu còn mới nhất. |
| Confirm và Back bị kích hoạt liên tiếp | Giao diện tuần tự hóa event; flow không nhận hai lệnh xung đột từ cùng vùng điều khiển. |
| Response mới nhất trả 403 hoặc 409 | Hiển thị trạng thái lỗi/phục hồi phù hợp, không chèn trang lỗi vào fragment. |
| Mất kết nối sau khi máy chủ commit | Retry cùng idempotency key không tạo giao dịch thứ hai. |
| Hai tab thao tác cùng hồ sơ | Máy chủ kiểm tra phiên bản/trạng thái nghiệp vụ và từ chối cập nhật xung đột phù hợp. |

Có thể dùng mock service hoặc test server để tạo độ trễ có kiểm soát: cho request A chờ lâu hơn request B, sau đó xác nhận vùng giao diện vẫn hiển thị dữ liệu B. Với command ghi dữ liệu, hãy kiểm tra số bản ghi và số lần gọi side effect trong cơ sở dữ liệu hoặc service mock, không chỉ kiểm tra số lần click handler chạy.

Trong kiểm thử Spring MVC/Web Flow, khởi chạy flow thật, giữ session và execution URL hợp lệ. Gửi các event theo trình tự dự kiến, kiểm tra redirect/fragment response, và xác nhận action chỉ chạy đúng số lần. Bổ sung kiểm thử tích hợp ở tầng service cho idempotency key và optimistic locking nếu nhiều người dùng có thể cập nhật cùng một tài nguyên.

## 9. Nguyên tắc thiết kế lâu dài

Chặn nhấn lặp tại giao diện để phản hồi nhanh và tránh gửi request dư. Bảo vệ side effect tại máy chủ bằng idempotency key, transaction và ràng buộc dữ liệu. Với request chỉ đọc, dùng request version để chỉ phản hồi mới nhất được cập nhật fragment; có thể kết hợp AbortController để giảm tải nhưng không coi abort là hủy giao dịch phía server.

Đối với event làm thay đổi flow state, hãy tuần tự hóa request trên cùng vùng điều khiển và xử lý rõ redirect, lỗi stale execution cùng trạng thái session. Với phản hồi AJAX, xác định hợp đồng fragment và chỉ cập nhật đúng vùng giao diện khi response còn phù hợp. Sự phối hợp này giúp hành trình Spring Web Flow ổn định khi người dùng thao tác nhanh, mạng chậm hoặc nhiều request hoàn tất theo thứ tự khác nhau.
