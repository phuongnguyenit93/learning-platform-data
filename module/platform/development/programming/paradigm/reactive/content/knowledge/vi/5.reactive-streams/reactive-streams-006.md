# Reactive Streams

## Nhu cầu cộng dồn, request không hợp lệ và nhu cầu không giới hạn

Trong Reactive Streams, Subscriber kiểm soát lượng dữ liệu muốn nhận bằng cách gọi **Subscription.request(n)**. Một lần gọi không chỉ cho phép Publisher gửi dữ liệu ngay tại thời điểm đó; nó bổ sung nhu cầu vào tổng nhu cầu của subscription. Publisher phải theo dõi số phần tử đã được yêu cầu nhưng chưa gửi, chỉ phát **onNext** trong giới hạn đó và xử lý những yêu cầu không hợp lệ theo hợp đồng.

Ba điểm cần nắm vững là: các lần **request** cộng dồn; **request** với số lượng không dương là vi phạm giao thức; và **Long.MAX_VALUE** biểu thị nhu cầu không giới hạn. Đây là những quy tắc cốt lõi để hiểu backpressure, đọc hành vi của Reactor và tránh vô tình cho phép một pipeline tiêu thụ dữ liệu không giới hạn.

### 1. Nhu cầu là số phần tử Subscriber được phép nhận

Sau khi Publisher gọi **onSubscribe(subscription)**, Subscriber có thể yêu cầu dữ liệu bằng **request(n)**. Tham số **n** là số phần tử mà Subscriber sẵn sàng tiếp nhận thêm. Publisher chỉ được gửi **onNext** khi còn nhu cầu đã được yêu cầu.

Ví dụ, nếu Subscriber gọi **request(3)**, Publisher có thể gửi tối đa ba phần tử theo subscription đó. Nếu nguồn chỉ có hai phần tử, Publisher có thể gửi hai **onNext** rồi kết thúc bằng **onComplete**. Nhu cầu còn dư không buộc Publisher phải tạo thêm dữ liệu.

Nhu cầu không phải là số byte, thời gian chờ hay số tác vụ đồng thời. Nó đếm số tín hiệu dữ liệu **onNext**. Một phần tử có thể rất nhỏ hoặc chứa một đối tượng lớn; do đó, giới hạn demand giúp kiểm soát số phần tử đang được yêu cầu nhưng không tự động đặt giới hạn chính xác cho bộ nhớ.

### 2. Các lần request được cộng dồn

Mỗi lần gọi **request(n)** hợp lệ bổ sung **n** vào nhu cầu của subscription. Publisher giảm nhu cầu còn lại đi một đơn vị mỗi khi gửi một **onNext**. Có thể hình dung:

\[
\text{Nhu cầu còn lại}
=
\text{Tổng request hợp lệ}
-
\text{Số onNext đã gửi}
\]

Ví dụ:

1. Subscriber gọi **request(2)**: Publisher được phép gửi tối đa hai phần tử.
2. Publisher gửi **onNext(A)** và **onNext(B)**: nhu cầu còn lại bằng không.
3. Subscriber gọi **request(3)**: Publisher được phép gửi thêm tối đa ba phần tử.
4. Tổng cộng, subscription đã được yêu cầu năm phần tử qua hai lần gọi.

Nếu Subscriber gọi **request(2)** rồi gọi tiếp **request(3)** trước khi Publisher phát phần tử nào, tổng nhu cầu đang chờ là năm. Nếu Publisher đã gửi hai phần tử trước lần gọi thứ hai, nhu cầu còn lại sau **request(3)** là ba. Vì vậy, cần phân biệt tổng số đã yêu cầu trong suốt vòng đời với nhu cầu còn lại tại một thời điểm.

Sơ đồ dưới đây minh họa trường hợp hai phần tử đầu đã được gửi trước khi yêu cầu tiếp:

~~~text
request(2) ──> demand = 2
                  |
                  +── onNext(A) ──> demand = 1
                  |
                  +── onNext(B) ──> demand = 0
                                      |
request(3) ───────────────────────────+
                                      v
                                  demand = 3
                                      |
                         onNext(C), onNext(D), onNext(E)
                                      |
                                  demand = 0
~~~

Các tín hiệu kết thúc **onComplete** và **onError** không tiêu thụ demand. Publisher có thể kết thúc một luồng rỗng mà không cần Subscriber yêu cầu phần tử nào. Ngược lại, Publisher không được gửi **onNext** vượt quá nhu cầu đã nhận.

### 3. Ví dụ yêu cầu theo từng đợt trong Reactor

**BaseSubscriber** cho phép chủ động điều khiển demand. Khi ghi đè **hookOnSubscribe**, Subscriber có thể yêu cầu một lượng ban đầu; sau khi xử lý một phần tử hoặc một nhóm phần tử, nó yêu cầu thêm:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

Flux<Integer> numbers = Flux.range(1, 5);

numbers.subscribe(new BaseSubscriber<Integer>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(2);
    }

    @Override
    protected void hookOnNext(Integer value) {
        System.out.println("Đã xử lý: " + value);

        if (value == 2) {
            request(3);
        }
    }
});
~~~

Subscriber yêu cầu hai phần tử đầu tiên. Sau khi nhận phần tử thứ hai, nó bổ sung ba phần tử demand. Với nguồn **Flux.range(1, 5)**, Publisher có thể gửi các giá trị từ 1 đến 5 rồi hoàn tất. Việc gọi **request(3)** trong callback của phần tử thứ hai minh họa rằng Subscriber có thể bổ sung nhu cầu khi đã xử lý xong một phần dữ liệu.

Trong Reactor, các dạng **subscribe** tiện lợi nhận lambda thường yêu cầu nhu cầu không giới hạn. Khi cần kiểm soát demand thủ công, hãy dùng **BaseSubscriber** hoặc một Subscriber tự cài đặt và gọi **request** theo chính sách cụ thể. Nếu ghi đè **hookOnSubscribe** của **BaseSubscriber**, cần tự gọi **request(n)**; không yêu cầu dữ liệu thì luồng sẽ không phát **onNext**.

### 4. Kiểm thử nhu cầu cộng dồn với StepVerifier

**StepVerifier** có thể thiết lập nhu cầu ban đầu và yêu cầu thêm trong quá trình kiểm thử. Điều này giúp xác nhận Publisher không phát vượt demand:

~~~java
StepVerifier.create(Flux.range(1, 5), 2)
    .expectNext(1, 2)
    .thenRequest(3)
    .expectNext(3, 4, 5)
    .verifyComplete();
~~~

Tham số **2** đặt nhu cầu ban đầu là hai phần tử. Sau khi xác nhận hai giá trị đầu, **thenRequest(3)** yêu cầu thêm ba phần tử. Kiểm thử xác nhận cả năm giá trị được phát đúng theo các đợt yêu cầu và luồng kết thúc bình thường.

Có thể dùng cùng cách tiếp cận để kiểm tra một pipeline có **limitRate**, **publishOn** hoặc toán tử kết hợp. Cần phân biệt nhu cầu của Subscriber cuối với cách một toán tử trung gian chia nhỏ hoặc đệm nhu cầu trước khi truyền lên upstream. Một toán tử có thể yêu cầu trước một lượng phần tử để hoạt động hiệu quả, nhưng vẫn phải tuân theo hợp đồng và giới hạn đã cấu hình.

### 5. Request không hợp lệ: số lượng phải lớn hơn không

Theo hợp đồng Reactive Streams, một yêu cầu chỉ hợp lệ khi **n** lớn hơn không. Nếu Subscriber gọi **request(0)** hoặc **request(-1)**, Publisher phải báo lỗi bằng **onError** với một **IllegalArgumentException**, miễn là subscription chưa bị hủy và chưa kết thúc.

Ví dụ về thao tác vi phạm:

~~~java
subscription.request(0); // Không hợp lệ: Publisher phải báo onError(IllegalArgumentException)
~~~

Yêu cầu không hợp lệ không có nghĩa Publisher được phép bỏ qua rồi tiếp tục phát dữ liệu như bình thường. Subscriber nên xem đây là lỗi giao thức và kiểm tra logic tính toán demand ở phía mình. Một lỗi thường gặp là truyền trực tiếp kết quả của phép tính có thể bằng không hoặc âm, chẳng hạn số lượng phần tử còn lại trong một trang đã xử lý hết.

Trước khi gọi **request**, hãy bảo đảm số lượng yêu cầu là số nguyên dương. Nếu số lượng cần yêu cầu được tính từ biến đếm hoặc cấu hình, nên xác thực giá trị trước khi truyền vào subscription. Sau khi subscription đã bị hủy hoặc kết thúc, yêu cầu tiếp theo không thể khởi động lại luồng đó.

### 6. Nhu cầu cộng dồn và tràn số

Nhu cầu được biểu diễn bằng kiểu **long**. Khi nhiều lần gọi **request(n)** được cộng lại, tổng có thể vượt giới hạn biểu diễn của **long**. Hợp đồng yêu cầu cách tính demand phải bão hòa ở **Long.MAX_VALUE**, không để phép cộng tràn vòng về số âm.

Ví dụ, nếu nhu cầu còn lại đang rất lớn và Subscriber tiếp tục yêu cầu thêm, tổng nhu cầu được xem là không giới hạn khi vượt khả năng biểu diễn:

~~~java
long currentDemand = Long.MAX_VALUE - 2;
long nextRequest = 10;

// Cộng demand theo kiểu bão hòa, không để tràn thành số âm.
long updatedDemand =
    currentDemand > Long.MAX_VALUE - nextRequest
        ? Long.MAX_VALUE
        : currentDemand + nextRequest;
~~~

Đoạn mã chỉ minh họa phép cộng bão hòa. Một Publisher thực tế còn phải xử lý đồng thời, tín hiệu kết thúc và việc hủy đăng ký; không nên dùng biến **long** thông thường nếu nhiều thread có thể cập nhật demand cùng lúc mà không có đồng bộ thích hợp.

### 7. Long.MAX_VALUE biểu thị nhu cầu không giới hạn

Subscriber có thể gọi:

~~~java
subscription.request(Long.MAX_VALUE);
~~~

Giá trị **Long.MAX_VALUE** được hiểu là nhu cầu không giới hạn (unbounded demand). Publisher không cần chờ Subscriber yêu cầu thêm sau mỗi phần tử và có thể phát tất cả phần tử mà nguồn cung cấp, cho đến khi hoàn tất, lỗi hoặc bị hủy.

Không nên hiểu nhu cầu không giới hạn là nguồn có vô hạn dữ liệu. Một **Flux.just(...)** hữu hạn vẫn phát đúng số phần tử trong nguồn rồi hoàn tất. Tương tự, một nguồn vô hạn có thể tiếp tục phát cho đến khi Subscriber hủy hoặc một lỗi xảy ra. **Long.MAX_VALUE** chỉ bỏ giới hạn demand của subscription; nó không thay đổi số dữ liệu thực tế mà nguồn có.

Nhu cầu không giới hạn thuận tiện cho các luồng hữu hạn, nhỏ hoặc khi consumer có khả năng xử lý toàn bộ tốc độ phát. Tuy nhiên, với nguồn sự kiện liên tục hoặc tốc độ cao, yêu cầu không giới hạn có thể làm mất lợi ích điều tiết của backpressure. Nếu downstream chậm hoặc có hàng đợi trung gian, bộ nhớ và độ trễ vẫn có thể tăng.

### 8. Phân biệt unbounded demand với buffer và concurrency

Ba khái niệm này thường xuất hiện cùng nhau nhưng kiểm soát những thứ khác nhau:

| Cơ chế | Kiểm soát điều gì? | Ví dụ |
| --- | --- | --- |
| Demand (**request(n)**) | Số phần tử Publisher được phép gửi | Subscriber yêu cầu thêm 20 phần tử |
| Buffer / prefetch | Số phần tử được giữ tạm hoặc yêu cầu trước tại một ranh giới | **publishOn** dùng hàng đợi để tách upstream và downstream |
| Concurrency | Số tác vụ con được xử lý đồng thời | **flatMap(mapper, concurrency)** giới hạn số publisher con đang hoạt động |

Yêu cầu unbounded demand không tự đặt giới hạn buffer hoặc concurrency. Ngược lại, giới hạn concurrency không nhất thiết có nghĩa subscriber cuối chỉ yêu cầu đúng số phần tử bằng concurrency; toán tử có thể có prefetch và chính sách replenishment riêng.

Khi cần kiểm soát tài nguyên, hãy xem toàn bộ pipeline: nguồn phát, toán tử có hàng đợi, prefetch, số tác vụ đồng thời và tốc độ consumer. Chỉ kiểm tra một lệnh **request** ở subscriber cuối là chưa đủ để kết luận tổng lượng dữ liệu đang được giữ trong bộ nhớ.

### 9. Quy tắc thực hành

Khi làm việc với demand trong Reactive Streams và Project Reactor, hãy ghi nhớ:

- Mỗi lần **request(n)** hợp lệ bổ sung **n** vào nhu cầu của subscription.
- Mỗi **onNext** tiêu thụ một đơn vị demand; tín hiệu kết thúc không tiêu thụ demand.
- Publisher không được phát **onNext** khi không còn nhu cầu.
- **request(0)** và **request(n)** với **n** âm là lỗi giao thức; Publisher phải báo **IllegalArgumentException** qua **onError** khi subscription còn hoạt động.
- Nhu cầu cộng dồn phải bão hòa ở **Long.MAX_VALUE** khi vượt giới hạn kiểu **long**.
- **Long.MAX_VALUE** biểu thị unbounded demand, không có nghĩa nguồn chắc chắn vô hạn.
- Chỉ dùng nhu cầu không giới hạn khi đã hiểu tốc độ nguồn, khả năng consumer và các vùng đệm trong pipeline.

Nắm được cách demand được cộng dồn và xác thực giúp ta đọc đúng hợp đồng Publisher–Subscriber. Đây cũng là cơ sở để hiểu backpressure ở các phần tiếp theo: Subscriber thể hiện khả năng tiếp nhận, Publisher tuân theo nhu cầu, còn các toán tử Reactor phối hợp việc yêu cầu trước, đệm và xử lý dữ liệu trong giới hạn tài nguyên của ứng dụng Java.
