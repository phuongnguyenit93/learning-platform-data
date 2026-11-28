# Rate limit

## 1. Mục tiêu và phạm vi

Rate limit là cơ chế giới hạn số lượng hoặc chi phí của các hành động được chấp nhận trong một khoảng thời gian, theo một phạm vi đã xác định. Phạm vi có thể là một địa chỉ mạng, người dùng, API key, tenant, nhóm API hoặc toàn bộ dịch vụ.

Trong thiết kế yêu cầu bảo mật, câu “API phải có rate limit” chưa cho biết hệ thống cần bảo vệ điều gì. Một giới hạn chỉ áp dụng trên từng instance có thể không đáp ứng ngân sách toàn cụm; một giới hạn chỉ theo IP có thể ảnh hưởng cả tổ chức dùng chung NAT; một giới hạn áp dụng sau truy vấn đắt tiền có thể quá muộn để bảo vệ tài nguyên đó.

Yêu cầu đầy đủ cần chỉ ra hành động được đếm, danh tính dùng để gom nhóm, thuật toán hoặc đặc tính giới hạn, ngưỡng, hành vi khi bị từ chối và bằng chứng kiểm chứng trong điều kiện đồng thời.

Sau bài này, người học có thể:

- Chuyển các rủi ro lạm dụng API và cạn kiệt tài nguyên thành chính sách giới hạn có thể đo được.
- Phân biệt tốc độ request, burst, số tác vụ đồng thời, hạn mức dài hạn và kích thước request.
- Chọn khóa đếm từ nguồn đáng tin cậy và xác định phạm vi toàn cụm.
- Hiểu đặc tính của fixed window, sliding window và token bucket.
- Đặc tả phản hồi khi vượt ngưỡng, hành vi khi bộ đếm lỗi và tiêu chí nghiệm thu.

Các giá trị số trong bài là ví dụ thiết kế để minh họa cách viết yêu cầu. Ngưỡng thực tế phải xuất phát từ năng lực hệ thống, hành vi hợp lệ, mức rủi ro và cam kết của sản phẩm.

## 2. Rate limit bảo vệ điều gì?

### 2.1. Tài nguyên và khả năng phục vụ

Một API tìm kiếm có thể phát sinh truy vấn cơ sở dữ liệu, một API export có thể tạo tệp lớn, còn một API gửi thông báo có thể tiêu thụ hạn mức của nhà cung cấp. Nếu caller có thể gọi không giới hạn, quyền sử dụng một chức năng có thể trở thành khả năng chiếm tài nguyên hoặc tạo chi phí vượt dự kiến.

Rate limit đặt một ngân sách cho hành vi theo thời gian. Ngân sách này hỗ trợ giữ khả năng phục vụ của các nhóm người dùng khác và làm cho mức sử dụng tài nguyên có giới hạn rõ hơn.

Tuy nhiên, rate limit không tự làm một request trở nên rẻ. Một request được cho phép vẫn có thể rất tốn tài nguyên nếu độ phức tạp truy vấn, kích thước dữ liệu hoặc số tác vụ con không được giới hạn.

### 2.2. Lạm dụng chức năng

Các hành vi như thử thông tin đăng nhập liên tục, gửi mã xác minh quá thường xuyên, quét dữ liệu hàng loạt hoặc tạo tác vụ tự động với tần suất cao đều có yếu tố thời gian và số lượng.

Giới hạn cần gắn với hành động nghiệp vụ thực sự. Nếu cùng một thao tác gửi mã có thể được gọi qua nhiều endpoint, đặt bộ đếm riêng trên từng URL có thể cho phép caller cộng dồn ngân sách ngoài ý muốn.

### 2.3. Tính công bằng

Một tenant có lượng sử dụng lớn không nên tự động tiêu thụ toàn bộ khả năng phục vụ của các tenant khác, trừ khi đó là hợp đồng chia sẻ tài nguyên đã được chấp nhận.

Có thể cần nhiều lớp ngân sách: theo người dùng để ngăn một tài khoản chiếm dụng, theo tenant để giữ cam kết tổ chức và toàn dịch vụ để bảo vệ năng lực hệ thống. Các lớp này có mục tiêu khác nhau, không nên được thay bằng một con số duy nhất.

## 3. Phân biệt những giới hạn dễ bị gộp chung

| Cơ chế | Câu hỏi được trả lời | Ví dụ |
| --- | --- | --- |
| Rate limit | Trong một khoảng thời gian, bao nhiêu hành động hoặc đơn vị chi phí được chấp nhận? | Tối đa một ngân sách gọi tìm kiếm theo người dùng |
| Burst allowance | Một đợt tăng tải ngắn được phép lớn đến mức nào? | Cho phép một nhóm request tức thời rồi giảm về tốc độ duy trì |
| Concurrency limit | Có bao nhiêu công việc đang chạy cùng lúc? | Mỗi tenant chỉ có hai job export đang thực thi |
| Quota | Tổng mức sử dụng trong chu kỳ dài là bao nhiêu? | Số lượt gửi thông báo trong một tháng |
| Giới hạn kích thước và độ phức tạp | Một request có thể lớn hoặc phức tạp đến đâu? | Giới hạn số ID trong batch hoặc độ sâu truy vấn |
| Timeout và giới hạn hàng đợi | Mỗi công việc có thể chiếm tài nguyên bao lâu và chờ bao lâu? | Hủy truy vấn quá hạn, không xếp hàng vô hạn |

Một API cho phép một request mỗi giây vẫn có thể có hàng trăm request đang chạy nếu mỗi request kéo dài nhiều phút. Vì vậy, rate limit và concurrency limit phải được thiết kế cùng nhau đối với công việc dài.

Tương tự, giới hạn 10 request mỗi phút không tương đương giới hạn 10 bản ghi được xử lý mỗi phút nếu mỗi request có thể chứa một triệu bản ghi. Khi chi phí phụ thuộc dữ liệu đầu vào, cần giới hạn độ lớn hoặc dùng đơn vị chi phí phù hợp do máy chủ xác định.

## 4. Những thành phần bắt buộc của một chính sách

Một chính sách có thể được mô tả bằng bộ thông tin:

```text
Hành động + Chủ thể/phạm vi + Đơn vị đếm + Ngân sách theo thời gian
    + Burst + Nơi thực thi + Hành vi vượt ngưỡng + Hành vi lỗi
```

### 4.1. Hành động được đếm

Cần nêu rõ đang đếm request đến, lần thử thực hiện, request đã được chấp nhận hay hành động hoàn tất thành công. Các lựa chọn này tạo ra hành vi rất khác nhau.

Ví dụ, với gửi mã xác minh, đếm số lần thực sự giao việc cho hệ thống gửi có thể phù hợp với ngân sách chi phí. Với chống thử thông tin đăng nhập, chỉ đếm lần đăng nhập thành công sẽ bỏ qua hành vi cần hạn chế.

Không nên tự động hoàn ngân sách cho mọi response lỗi. Một request không hợp lệ hoặc gây lỗi vẫn có thể đã tiêu thụ tài nguyên; việc hoàn ngân sách có thể cho phép lặp lại công việc đắt tiền mà không chạm ngưỡng.

### 4.2. Khóa đếm và phạm vi

Một khóa hợp lý có thể gồm định danh policy, phiên bản policy, tenant đã xác minh, subject đã xác minh và nhóm hành động chuẩn hóa.

```text
policy=requirement-search
tenant=tenant-A
subject=user-108
action-group=requirement.search
```

Không nhất thiết lưu khóa dưới dạng chuỗi thô như ví dụ. Điều quan trọng là cùng một phạm vi nghiệp vụ phải đi tới cùng bộ đếm, còn các phạm vi cần độc lập không vô tình dùng chung ngân sách.

### 4.3. Ngưỡng và đơn vị thời gian

“100 request” thiếu một đơn vị thời gian. “100 request/phút” vẫn cần nói đó là phút cố định, bất kỳ cửa sổ 60 giây nào hay tốc độ duy trì với burst.

Đối với token bucket, cần cả dung lượng bucket và tốc độ nạp. Nếu chỉ nêu tốc độ nạp, không thể suy ra số request được phép gửi ngay khi bucket đầy.

### 4.4. Phạm vi triển khai

Yêu cầu phải nói giới hạn là trên một process, một instance, một vùng triển khai hay toàn cụm phục vụ. Tăng số instance không được vô tình nhân ngân sách nếu sản phẩm cam kết một giới hạn toàn cụm.

Nếu thiết kế cho phép một mức vượt ngưỡng do đồng bộ phân tán, phải ghi rõ độ vượt cho phép và điều kiện áp dụng. Không mô tả một giới hạn gần đúng như một bảo đảm tuyệt đối.

### 4.5. Hành vi vượt ngưỡng và khi lỗi

Hệ thống cần xác định có từ chối ngay, trì hoãn trong một hàng đợi hữu hạn hay áp dụng cơ chế điều tiết khác. Với API tương tác, từ chối trước khi chạy công việc đắt tiền thường giúp caller và hệ thống kiểm soát tốt hơn việc chờ.

Khi kho bộ đếm hoặc dịch vụ quyết định không hoạt động, hành vi phải được quy định riêng. Mất khả năng kiểm tra giới hạn không được âm thầm biến thành một ngân sách vô hạn ngoài hợp đồng bảo mật.

## 5. Chọn danh tính dùng để gom nhóm

### 5.1. Caller chưa được xác thực

Trước khi nhận diện được người dùng, hệ thống có thể cần giới hạn theo nguồn mạng và nhóm hành động để bảo vệ chính quá trình xác thực. Tuy nhiên, IP chỉ là một tín hiệu, không phải định danh chắc chắn của một người.

Nhiều người dùng hợp lệ có thể dùng chung IP qua NAT hoặc proxy. Ngược lại, một bên lạm dụng có thể tạo request từ nhiều nguồn. Vì vậy, chính sách chỉ theo IP cần được đánh giá về cả khả năng bỏ qua lẫn ảnh hưởng đến người dùng dùng chung mạng.

### 5.2. Caller đã được xác thực

Sau xác thực, có thể áp dụng thêm ngân sách theo subject, API key hoặc tenant đã được xác minh. ID người dùng do body gửi lên không được tự chọn bộ đếm của người khác hoặc tạo vô hạn danh tính mới.

Nếu dùng API key làm căn cứ, nên dùng định danh của key hoặc một biểu diễn phù hợp thay vì đưa nguyên secret vào log và khóa vận hành. Nếu mỗi key có ngân sách riêng, cần quyết định người sở hữu có thể tạo nhiều key để cộng ngân sách hay không.

### 5.3. Header chuyển tiếp từ proxy

Không tin một header như `X-Forwarded-For` chỉ vì nó có mặt. Hệ thống cần biết proxy nào được tin cậy, cách proxy ghi hoặc thay header và cách xác định địa chỉ client trong chuỗi chuyển tiếp.

Nếu caller tự khai được địa chỉ dùng để đếm, họ có thể thay khóa theo từng request. Nếu ứng dụng chỉ thấy địa chỉ của một reverse proxy, mọi người dùng có thể bị gom vào cùng một bucket ngoài ý muốn.

### 5.4. Chuẩn hóa endpoint và giới hạn số lượng khóa

Không dùng toàn bộ URL thô làm tên policy. Các giá trị query khác nhau hoặc ID khác nhau trong đường dẫn có thể tạo bộ đếm mới dù chúng thực hiện cùng một hành động.

```text
/requirements/req-108
/requirements/req-109
```

Hai đường dẫn trên thường cùng thuộc một route chuẩn hóa hoặc nhóm hành động. Việc có giới hạn riêng trên từng tài nguyên hay không phải là quyết định chính sách, không phải hệ quả ngẫu nhiên của cách ghép chuỗi khóa.

Kho bộ đếm cũng cần ngân sách về bộ nhớ, thời gian sống và cơ chế dọn khóa. Một limiter tạo một entry không bao giờ xóa cho mỗi chuỗi caller tự chọn có thể trở thành nguồn cạn tài nguyên mới.

## 6. Các thuật toán và đặc tính cần hiểu

### 6.1. Fixed window

Fixed window đếm số hành động trong các khoảng cố định, chẳng hạn từng phút theo một mốc đã xác định. Khi sang cửa sổ mới, ngân sách được cấp lại theo chính sách.

Ưu điểm là mô hình đơn giản. Hạn chế là burst quanh ranh giới: với 100 request/phút, caller có thể gửi gần 100 request ở cuối phút trước và gần 100 request ở đầu phút sau trong một khoảng ngắn.

Nếu yêu cầu là “không quá 100 trong bất kỳ 60 giây liên tiếp”, fixed window đơn giản không đáp ứng được bảo đảm đó. Chỉ đổi tên cửa sổ không giải quyết khác biệt thuật toán.

### 6.2. Sliding window

Sliding window đánh giá một khoảng thời gian trượt theo thời điểm hiện tại. Cách lưu thời điểm từng hành động có thể cho kết quả sát với hợp đồng cửa sổ nhưng tốn dữ liệu; cách dùng các bộ đếm tổng hợp có thể là gần đúng.

Khi chọn một biến thể, cần ghi rõ độ chính xác mong muốn và ngân sách tài nguyên. Tên “sliding window” chưa đủ để kết luận mọi triển khai đều có cùng bảo đảm.

### 6.3. Token bucket

Token bucket có dung lượng tối đa `B` và tốc độ nạp `r` token mỗi giây. Một request tiêu thụ một hoặc nhiều token theo chính sách. Nếu không đủ token, request không được chấp nhận ở thời điểm đó.

Với một request giá một token:

```text
token mới = min(B, token hiện có + r × thời gian đã qua)

nếu token mới >= 1:
    chấp nhận và trừ 1
ngược lại:
    từ chối tại thời điểm hiện tại
```

Bucket đầy cho phép burst tới `B` đơn vị. Sau khi sử dụng hết, ngân sách được phục hồi theo tốc độ `r`, không cần chờ một mốc reset chung.

Trong một mô hình token bucket lý tưởng, lượng công việc được chấp nhận trong khoảng thời gian dài `Δt` được chặn trên bởi ngân sách ban đầu cộng phần nạp, tối đa `B + r × Δt`. Đây là bảo đảm khác với “không quá B request trong mọi cửa sổ cố định”.

### 6.4. Bảng so sánh theo yêu cầu

| Mô hình | Đặc tính nổi bật | Điều cần đặc tả |
| --- | --- | --- |
| Fixed window | Đếm theo mốc; có thể có burst ở ranh giới | Mốc cửa sổ, giới hạn và burst được chấp nhận |
| Sliding window theo sự kiện | Xét các hành động trong cửa sổ gần nhất | Kích thước cửa sổ, xử lý ranh giới, chi phí lưu sự kiện |
| Sliding window tổng hợp | Tiết kiệm trạng thái hơn trong một số thiết kế | Sai số hoặc độ vượt được chấp nhận |
| Token bucket | Tách tốc độ duy trì khỏi dung lượng burst | Dung lượng, tốc độ nạp, giá mỗi hành động, trạng thái khởi tạo |
| Điều tiết qua hàng đợi | Có thể làm đều tốc độ xử lý | Dung lượng hàng đợi, thời gian chờ, hủy và phản hồi khi đầy |

Lựa chọn thuật toán nên theo đặc tính sản phẩm cần bảo đảm. Không nên chọn chỉ vì tên thuật toán quen thuộc rồi viết yêu cầu theo một mô hình khác.

## 7. Đặc tả yêu cầu bảo mật cho một API mẫu

Giả sử API tìm kiếm yêu cầu bảo mật có chi phí tương đối ổn định và cần cho phép một số thao tác liên tiếp khi người dùng mở màn hình.

### 7.1. Một đặc tả cụ thể

```text
REQ-RATE-01 — Ngân sách tìm kiếm theo chủ thể

Đối với request tìm kiếm hợp lệ đã có subject và tenant được xác minh,
hệ thống áp dụng một token bucket cho mỗi cặp tenant/subject trong nhóm
hành động requirement.search, trên toàn cụm phục vụ.

Dung lượng bucket: 20 token.
Tốc độ nạp: 10 token/giây.
Giá một request được chấp nhận: 1 token.
Trạng thái khởi tạo: đầy bucket.

Chỉ chấp nhận request khi thao tác kiểm tra và trừ token thành công.
Không hoàn token theo kết quả nghiệp vụ của request đã được chấp nhận.
Request bị từ chối do thiếu token không chạy truy vấn tìm kiếm.
```

Đặc tả trên nói rõ burst và cách đếm. Nó không nói “chỉ được 20 request trong mỗi giây”: một bucket đầy cộng phần nạp trong giây đó có thể chấp nhận nhiều hơn 20 theo thời điểm đến.

### 7.2. Các yêu cầu bổ sung

| Mã | Yêu cầu | Bằng chứng nghiệm thu |
| --- | --- | --- |
| REQ-RATE-02 | Khóa đếm sử dụng tenant và subject đã xác minh; thay trường tự khai trong request không tạo thêm ngân sách | Luồng tạo khóa và các request thay giá trị tự khai |
| REQ-RATE-03 | Các instance chia sẻ cùng phạm vi ngân sách theo hợp đồng toàn cụm | Kết quả request đồng thời đi qua nhiều instance |
| REQ-RATE-04 | Quyết định chấp nhận và tiêu thụ ngân sách phải có tính nguyên tử phù hợp với bảo đảm đã công bố | Kịch bản nhiều request cùng tranh phần ngân sách cuối |
| REQ-RATE-05 | Response vượt ngưỡng dùng hợp đồng lỗi nhất quán và không thực hiện công việc được bảo vệ | Response và số lần gọi thành phần tìm kiếm |
| REQ-RATE-06 | Kho trạng thái có giới hạn tài nguyên, thời gian sống và quy tắc dọn khóa không tạo lại ngân sách sớm ngoài hợp đồng | Chính sách vòng đời bucket và quan sát tài nguyên |
| REQ-RATE-07 | Lỗi bộ đếm không dẫn tới nhánh mặc định cấp ngân sách không giới hạn | Kịch bản timeout hoặc mất kết nối kho trạng thái |
| REQ-RATE-08 | Thay đổi ngưỡng phải có phiên bản, chủ sở hữu và cách chuyển trạng thái đếm đã xác định | Cấu hình policy và kết quả chuyển phiên bản |

Nếu cần giới hạn thêm theo tenant hoặc toàn dịch vụ, phải bổ sung chính sách riêng. Khi một request chịu nhiều ngân sách, cần xác định thứ tự kiểm tra và việc ngân sách của lớp trước có bị tiêu thụ khi lớp sau từ chối hay không.

Không mặc định nhiều bộ đếm độc lập cùng tạo thành một transaction. Nếu sản phẩm cần bảo đảm “chỉ trừ tất cả khi mọi điều kiện đều cho phép”, cách thực thi phải đáp ứng chính xác bảo đảm đó.

## 8. Ví dụ Java: token bucket trong một process

Ví dụ dưới đây minh họa một bucket, giá mỗi lần gọi là một token. Nó dùng đồng hồ đơn điệu cho thời gian đã qua và đồng bộ hóa thao tác nạp, kiểm tra, trừ token trong cùng một đối tượng.

```java
public final class LocalTokenBucket {

    public record Decision(boolean allowed, long retryAfterNanos) {
    }

    private final int capacity;
    private final double refillPerSecond;

    private double tokens;
    private long lastRefillNanos;

    public LocalTokenBucket(int capacity, double refillPerSecond) {
        if (capacity <= 0) {
            throw new IllegalArgumentException("capacity must be positive");
        }

        if (!Double.isFinite(refillPerSecond) || refillPerSecond <= 0) {
            throw new IllegalArgumentException("invalid refill rate");
        }

        this.capacity = capacity;
        this.refillPerSecond = refillPerSecond;
        this.tokens = capacity;
        this.lastRefillNanos = System.nanoTime();
    }

    public synchronized Decision tryAcquire() {
        long now = System.nanoTime();
        long elapsedNanos = now - lastRefillNanos;

        if (elapsedNanos > 0) {
            double elapsedSeconds = elapsedNanos / 1_000_000_000.0;
            tokens = Math.min(
                    capacity,
                    tokens + elapsedSeconds * refillPerSecond);
            lastRefillNanos = now;
        }

        if (tokens >= 1.0) {
            tokens -= 1.0;
            return new Decision(true, 0);
        }

        double waitSeconds = (1.0 - tokens) / refillPerSecond;
        long retryNanos = (long) Math.ceil(waitSeconds * 1_000_000_000.0);

        return new Decision(false, Math.max(1L, retryNanos));
    }
}
```

Một caller trong cùng process có thể sử dụng:

```java
LocalTokenBucket bucket = new LocalTokenBucket(20, 10.0);
LocalTokenBucket.Decision decision = bucket.tryAcquire();

if (!decision.allowed()) {
    // Trả kết quả vượt ngưỡng theo hợp đồng API.
    // Không gọi công việc nghiệp vụ được bucket này bảo vệ.
    return;
}

// Thực hiện đúng một đơn vị công việc đã được chấp nhận.
```

Đối tượng bucket trong đoạn sử dụng phải được giữ và tái sử dụng cho đúng phạm vi. Nếu tạo một bucket đầy mới cho mỗi request, mọi request đều nhận ngân sách mới và giới hạn không còn ý nghĩa.

### 8.1. Ý nghĩa của các lựa chọn trong ví dụ

- `System.nanoTime()` được dùng để đo khoảng thời gian trong process, thay vì dùng ngày giờ theo lịch có thể được điều chỉnh.
- `synchronized` giữ thao tác đọc và cập nhật trạng thái của cùng một bucket khỏi tranh chấp giữa các thread trong process đó.
- Bucket khởi tạo đầy vì đó là hợp đồng đã chọn. Một policy khác có thể cần cách khởi tạo khác.
- Request bị từ chối không trừ thêm token trong mô hình này; request đã được chấp nhận tiêu thụ một token bất kể kết quả nghiệp vụ sau đó.
- `retryAfterNanos` chỉ là thời gian ước tính tới lúc đủ một token nếu không có request khác tiêu thụ trước.

### 8.2. Giới hạn của ví dụ

Đây là một bucket cục bộ, không có kho dùng chung, vòng đời khóa, khôi phục trạng thái sau restart hoặc chính sách đa tenant. `synchronized` không tạo tính nguyên tử giữa hai instance hay hai process.

Ví dụ dùng số thực để giải thích nạp token. Với yêu cầu kế toán hoặc biên chính xác nghiêm ngặt, cần chọn biểu diễn số và xử lý làm tròn phù hợp, rồi kiểm chứng theo hợp đồng. Không suy ra một bảo đảm phân tán nghiêm ngặt chỉ từ một lớp minh họa trong bộ nhớ.

Ứng dụng thực tế cũng cần giới hạn cấu hình ở miền giá trị vận hành hợp lý. Việc một giá trị là số hữu hạn không tự chứng minh đó là tốc độ phù hợp với độ phân giải thời gian, tài nguyên hoặc cam kết sản phẩm.

## 9. Thực thi trong kiến trúc API

### 9.1. Đặt kiểm tra trước công việc cần bảo vệ

Một luồng có thể gồm:

```text
Giới hạn sơ bộ ở biên theo nguồn và nhóm hành động
    → kiểm tra kích thước và cấu trúc request theo hợp đồng
    → xác thực và xác lập subject/tenant
    → áp dụng ngân sách theo danh tính đã xác minh
    → kiểm tra quyền cho hành động và tài nguyên
    → thực hiện công việc trong các giới hạn tài nguyên khác
```

Đây là sơ đồ minh họa, không phải thứ tự duy nhất cho mọi API. Một số quyết định cần được thực hiện sớm để bảo vệ authentication; một số cần biết quyền hoặc đối tượng trước khi tính chi phí. Thiết kế phải chỉ rõ mỗi lớp bảo vệ phần công việc nào và request bị từ chối ở lớp nào được đếm ra sao.

Nếu rate limit chỉ chạy sau truy vấn tìm kiếm nặng, nó chưa bảo vệ tài nguyên mà truy vấn đã tiêu thụ. Nếu chỉ có giới hạn sau xác thực, lượng request chưa xác thực vẫn có thể gây áp lực lên thành phần xác thực.

### 9.2. Kiểm tra và cập nhật phải đi cùng nhau

Mô hình đọc số dư rồi cập nhật bằng hai thao tác độc lập có thể cho nhiều request cùng thấy phần ngân sách cuối và cùng được chấp nhận.

```text
Request A đọc: còn 1 token.
Request B đọc: còn 1 token.
A chấp nhận.
B chấp nhận.
```

Để đáp ứng giới hạn đã công bố, cần một thao tác hoặc giao thức có tính nguyên tử phù hợp cho việc đánh giá và tiêu thụ ngân sách. Cách triển khai cụ thể phụ thuộc kho trạng thái; không nên coi tính nguyên tử của một lệnh riêng lẻ là bằng chứng cho cả chuỗi nhiều lệnh.

Đồng hồ cũng là một phần của thiết kế phân tán. Các giá trị từ `System.nanoTime()` của hai process không tạo thành một mốc chung để lưu và so sánh trực tiếp. Một limiter phân tán cần một mô hình thời gian và nguồn thời gian được xác định cho chính nó.

### 9.3. Scale, restart và vòng đời bucket

Nếu mỗi instance có bucket đầy 20 token, ba instance có thể cấp tổng ngân sách lớn hơn một bucket 20 token. Phân phối tải không biến các bucket đó thành một bucket toàn cụm.

Restart cũng có thể cấp lại burst nếu trạng thái chỉ nằm trong bộ nhớ. Nếu điều đó nằm ngoài hợp đồng, cần lưu trạng thái hoặc chọn cách khôi phục phù hợp. Nếu thiết kế chấp nhận ngân sách cấp lại khi restart, phải định nghĩa rõ thay vì bỏ ngỏ.

TTL của bucket không được làm ngân sách phục hồi nhanh hơn policy. Ví dụ, xóa một bucket chưa đầy rồi tạo lại bucket đầy có thể cấp thêm token mà thời gian nạp chưa cho phép. Cơ chế dọn cần biết khi nào bỏ trạng thái không làm thay đổi bảo đảm đã chọn.

### 9.4. Chi phí có trọng số

Nếu một request có thể tạo nhiều công việc, policy có thể tính theo đơn vị chi phí thay vì chỉ đếm request. Chi phí phải được tính hoặc xác minh ở phía máy chủ.

Không để caller gửi `cost=1` cho một batch rất lớn rồi coi đó là số liệu đáng tin. Cần giới hạn batch, tính chi phí từ kích thước đã kiểm tra và quyết định thời điểm giữ ngân sách trước khi thực hiện.

Nếu ước tính chi phí trước và quyết toán sau, phải đặc tả ngân sách giữ chỗ, hoàn phần không dùng và xử lý request thất bại. Rate limit đếm request đơn giản không tự cung cấp các bảo đảm này.

## 10. Hợp đồng khi vượt giới hạn hoặc khi limiter lỗi

### 10.1. Phản hồi vượt ngưỡng

Với API HTTP từ chối do caller đã vượt giới hạn áp dụng, có thể sử dụng response như:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Cache-Control: no-store
Retry-After: 2

{
  "code": "RATE_LIMITED",
  "message": "Tần suất yêu cầu vượt giới hạn cho phép.",
  "requestId": "req-example-108"
}
```

`Retry-After: 2` trong ví dụ biểu diễn thời gian chờ theo giây. Nếu chọn biểu diễn này, thời gian tính được cần làm tròn phù hợp để không khuyến khích caller thử lại sớm hơn dự kiến. API không cần công khai chi tiết định danh người dùng, tenant, số dư của chủ thể khác hoặc cấu trúc kho bộ đếm.

Thời gian chờ là hướng dẫn tại thời điểm ra quyết định, không phải lời hứa giữ sẵn token cho lần thử tiếp theo. Request khác hoặc một policy khác vẫn có thể khiến lần gọi sau bị từ chối.

### 10.2. Client cần kiểm soát retry

Nếu nhiều client cùng thử lại ngay khi hết thời gian chờ, hệ thống có thể nhận một đợt tăng tải mới. Hợp đồng client có thể yêu cầu tôn trọng hướng dẫn chờ, dùng backoff, thêm độ lệch thời gian và giới hạn tổng số lần retry.

Đối với thao tác ghi, client còn cần biết việc retry có thể lặp tác động hay không. Rate limit không thay thế idempotency hoặc cơ chế chống xử lý trùng của thao tác nghiệp vụ.

Không khắc phục vượt giới hạn bằng cách giữ mọi HTTP thread ngủ cho tới khi có token. Nếu sản phẩm chọn xếp hàng, hàng đợi phải có giới hạn số lượng, thời gian chờ, hủy và hành vi khi đầy.

### 10.3. Lỗi limiter khác với hết ngân sách

Timeout khi đọc bộ đếm không chứng minh caller đã vượt ngưỡng. API có thể trả một lỗi khả dụng theo hợp đồng đã chọn, thay vì gắn mọi sự cố thành 429 và gây hiểu nhầm về nguyên nhân.

Với hành động rủi ro cao hoặc có chi phí khó phục hồi, có thể yêu cầu không thực hiện khi không xác nhận được ngân sách. Với một chức năng khác, thiết kế có thể cho phép cơ chế dự phòng hữu hạn, chẳng hạn ngân sách cục bộ bảo thủ trong một khoảng thời gian xác định.

Mọi dự phòng phải có giới hạn, điều kiện kích hoạt và cách trở lại trạng thái bình thường. Nếu dự phòng phá vỡ bảo đảm toàn cụm trong thời gian sự cố, đây là ngoại lệ cần được mô tả rõ theo mức rủi ro được chấp nhận.

### 10.4. Tránh biến giới hạn thành khóa tài khoản tùy ý

Một bên có thể thử làm cạn ngân sách của danh tính khác nếu khóa đếm được xây từ một giá trị chưa xác minh, chẳng hạn tên đăng nhập trong request. Không nên từ đó kết luận mọi chính sách theo tài khoản là sai; cần đánh giá tác động từ chối dịch vụ và phối hợp nhiều tín hiệu phù hợp.

Yêu cầu cho luồng đăng nhập hoặc gửi mã nên xét cả lạm dụng lẫn khả năng phục hồi của người dùng hợp lệ. Cần tránh phản hồi vô tình tiết lộ tài khoản có tồn tại hay không hoặc tạo cơ chế khóa kéo dài mà bất kỳ ai cũng kích hoạt được.

## 11. Tiêu chí nghiệm thu có thể đo được

### 11.1. Kiểm chứng đúng mô hình thời gian

Với bucket dung lượng 20 và tốc độ nạp 10 token/giây, trong mô hình thời gian được kiểm soát:

| Tình huống | Kỳ vọng |
| --- | --- |
| Bucket mới đầy, 20 lần gọi không có thời gian nạp xen giữa | Chấp nhận 20 đơn vị |
| Lần gọi tiếp theo tại cùng thời điểm | Từ chối do thiếu token |
| Sau 50 ms kể từ lúc bucket hết | Chưa đủ một token mới |
| Sau 100 ms kể từ lúc bucket hết, không có lần tiêu thụ khác | Đủ ngân sách cho một đơn vị |
| Không sử dụng trong thời gian dài | Số token không vượt dung lượng 20 |
| Tạo request với tenant hoặc subject khác đã xác minh | Áp dụng bucket tương ứng theo hợp đồng |

Trong kiểm chứng thuật toán, nên điều khiển được thời gian hoặc nguồn thời gian để tránh kết luận sai do độ trễ thực thi. Nếu gửi 21 request ngoài đời theo thứ tự, thời gian giữa chúng có thể đã nạp lại token; không thể mặc định request thứ 21 luôn phải bị từ chối.

### 11.2. Đồng thời và nhiều instance

```text
Given:
  Một phạm vi tenant/subject còn đúng một token.
  Việc nạp token trong khoảng kiểm chứng được kiểm soát hoặc tính tới.
  Nhiều request cùng tới các instance phục vụ.

When:
  Các request đồng thời tranh ngân sách cuối đó.

Then:
  Số đơn vị được chấp nhận không vượt ngân sách được phép theo mô hình.
  Request bị từ chối không gọi công việc được limiter bảo vệ.
  Tổng kết quả trên mọi instance đáp ứng cùng phạm vi đã công bố.
```

Nếu thiết kế là gần đúng, tiêu chí phải thay bằng giới hạn sai số cụ thể. Chỉ quan sát không có exception hoặc bộ đếm không âm chưa chứng minh số request được chấp nhận là đúng.

### 11.3. Các tình huống cần có trong ma trận

| Nhóm | Tình huống đại diện | Điều cần quan sát |
| --- | --- | --- |
| Ranh giới ngân sách | Còn đủ, vừa hết, chưa nạp đủ, đã nạp đủ | Số đơn vị chấp nhận và thời gian thử lại |
| Ranh giới cửa sổ | Gọi sát hai bên mốc reset nếu dùng fixed window | Burst thực tế đúng hợp đồng |
| Danh tính | Đổi trường tự khai, API key hoặc header nguồn | Không tự tạo ngân sách ngoài quyền |
| Phạm vi | Người dùng khác, tenant khác, nhiều instance | Độc lập hoặc dùng chung đúng thiết kế |
| Tác động | Request bị từ chối gọi API đắt tiền | Không tạo công việc hoặc tác động bị cấm |
| Kho trạng thái | Timeout, mất kết nối, khôi phục | Đúng chế độ lỗi và dự phòng đã chọn |
| Vòng đời | Restart, scale và dọn bucket | Không cấp lại ngân sách ngoài hợp đồng |
| Client | Retry sau 429 và lặp thao tác ghi | Không tạo retry vô hạn hoặc tác động trùng ngoài thiết kế |

### 11.4. Bằng chứng cần gắn với yêu cầu

Bằng chứng có thể gồm cấu hình policy, luồng tạo khóa, kết quả kiểm chứng thời gian và đồng thời, số lần gọi thành phần nghiệp vụ cùng quan sát trạng thái kho bộ đếm.

Một kiểm thử đơn vị của bucket chỉ chứng minh thuật toán cục bộ trong điều kiện đã kiểm tra. Nó chưa chứng minh mọi route đi qua limiter, danh tính được lấy đúng hoặc nhiều instance dùng cùng ngân sách.

Một lần nhận 429 cũng chưa chứng minh hệ thống được bảo vệ. Phải xác nhận response đó xuất phát từ policy dự kiến và công việc cần bảo vệ chưa được thực hiện trước khi bị từ chối.

## 12. Quan sát vận hành và thay đổi policy

### 12.1. Chỉ số có ích

Có thể theo dõi số request được chấp nhận, số bị từ chối, thời gian quyết định, lỗi kho trạng thái, lượng khóa đang tồn tại và mức sử dụng tài nguyên của limiter. Các chỉ số cần giúp phân biệt caller thực sự vượt ngân sách với lỗi thành phần hạ tầng.

Không gắn mọi `userId`, URL thô hoặc giá trị request tùy ý thành nhãn metric. Số lượng nhãn không được kiểm soát có thể làm tăng chi phí và tài nguyên của chính hệ thống quan sát.

Log hoặc trace chi tiết theo request cần có chính sách bảo vệ dữ liệu, giới hạn lượng ghi và thời gian lưu. Không ghi access token, API secret hoặc toàn bộ thông tin nhận diện chỉ để điều tra một response 429.

### 12.2. Đánh giá ảnh hưởng tới người dùng hợp lệ

Tỷ lệ 429 cao có thể phản ánh lạm dụng, ngưỡng không phù hợp, client retry lỗi hoặc nhiều người bị gom chung khóa. Chỉ tăng ngưỡng mà không xem nguyên nhân có thể che vấn đề thiết kế.

Cần quan sát các nhóm người dùng có chung mạng, tenant lớn và các hành vi burst hợp lệ. Mục tiêu là ngân sách bảo vệ rủi ro được đặc tả trong khi vẫn đáp ứng hợp đồng phục vụ, không phải tối đa hóa số request bị chặn.

### 12.3. Thay đổi cấu hình không được ngẫu nhiên cấp ngân sách mới

Khi đổi dung lượng hoặc tốc độ nạp, phải quyết định cách chuyển trạng thái bucket đang tồn tại. Đổi tên policy khiến mọi khóa trở thành mới và đầy có thể tạo một đợt cấp lại burst ngoài dự kiến.

Nếu sản phẩm muốn chủ động cấp lại ngân sách khi thay policy, đó phải là hành vi có chủ ý. Triển khai luân phiên nhiều phiên bản cần tránh việc caller nhận riêng ngân sách từ từng phiên bản trong thời gian chuyển tiếp nếu hợp đồng không cho phép.

## 13. Hồ sơ yêu cầu mẫu

Một hồ sơ có thể dùng để thiết kế và nghiệm thu API tìm kiếm:

```text
Tài sản cần bảo vệ:
  Năng lực truy vấn và khả năng phục vụ công bằng giữa các chủ thể.

Hành động:
  requirement.search qua mọi route được ánh xạ tới nhóm hành động này.

Phạm vi đếm:
  Mỗi tenant/subject đã được xác minh, trên toàn cụm phục vụ.

Ngân sách:
  Token bucket đầy lúc khởi tạo; dung lượng 20; nạp 10 token/giây.
  Mỗi request được chấp nhận tiêu thụ một token và không hoàn theo kết quả.

Thực thi:
  Kiểm tra và tiêu thụ ngân sách trước truy vấn tìm kiếm.
  Thao tác quyết định bảo đảm tính nguyên tử theo hợp đồng toàn cụm.
  Từ chối không được tạo công việc tìm kiếm.

Phản hồi:
  Vượt ngân sách trả 429 theo schema lỗi; hướng dẫn chờ khi tính được.
  Lỗi limiter có hợp đồng riêng và không cấp ngân sách vô hạn.

Bằng chứng:
  Cấu hình, nguồn danh tính, ranh giới thời gian, đồng thời, nhiều instance,
  lỗi kho trạng thái, vòng đời bucket và số lần gọi công việc nghiệp vụ.
```

Rate limit đáp ứng mục tiêu khi ngân sách được áp dụng đúng cho hành động, danh tính và phạm vi đã công bố, kể cả lúc đồng thời hoặc có sự cố. Một yêu cầu bảo mật có thể kiểm chứng phải mô tả cả lượng công việc được chấp nhận lẫn điều gì không được xảy ra khi ngân sách không còn.
