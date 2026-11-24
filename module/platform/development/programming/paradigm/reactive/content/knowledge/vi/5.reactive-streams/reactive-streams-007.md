# Quan hệ giữa số phần tử yêu cầu và số phần tử được phát

Trong Reactive Streams, subscriber điều khiển tốc độ nhận dữ liệu bằng cách gọi request(n) trên Subscription. Con số n biểu thị số phần tử mà subscriber sẵn sàng nhận thêm. Publisher phải tôn trọng nhu cầu đó: tổng số phần tử phát qua onNext không được vượt quá tổng số phần tử đã được yêu cầu cho subscription tương ứng.

Quy tắc này là nền tảng của backpressure. Nó giúp một consumer xử lý chậm có thể giới hạn lượng dữ liệu được chuyển đến mình, thay vì để publisher phát vô hạn và làm tăng hàng đợi hoặc bộ nhớ. Trong hệ sinh thái Java, Reactor hiện thực hợp đồng này cho Mono và Flux; các toán tử có thể phối hợp nhu cầu giữa downstream và upstream để điều tiết một pipeline.

## 1. Nhu cầu dữ liệu là gì?

Khi subscriber nhận onSubscribe(subscription), nó có thể gọi subscription.request(n). Đây là yêu cầu phát thêm tối đa n phần tử. Nhu cầu được tính riêng cho từng subscription, vì mỗi lần subscribe tạo ra một quan hệ điều khiển độc lập.

Ví dụ, nếu subscriber gọi request(3), publisher được phép phát tối đa ba phần tử qua onNext theo nhu cầu hiện tại. Sau khi phát ba phần tử, publisher phải chờ thêm nhu cầu trước khi phát phần tử tiếp theo. Nếu subscriber tiếp tục gọi request(2), publisher có thể phát thêm tối đa hai phần tử.

Điểm quan trọng là request(n) biểu thị **mức nhu cầu**, không phải lệnh bắt buộc publisher phải lập tức phát đủ n phần tử. Publisher có thể phát ít hơn nếu nguồn chỉ còn ít dữ liệu, nguồn hoàn tất sớm hoặc xảy ra lỗi. Nếu nguồn không có dữ liệu, publisher có thể gửi onComplete mà không cần phát onNext nào.

Các tín hiệu kết thúc không tiêu thụ nhu cầu. Publisher có thể gửi onComplete hoặc onError ngay cả khi subscriber chưa yêu cầu phần tử nào. Nhu cầu chỉ giới hạn số lần phát onNext.

## 2. Quy tắc đếm giữa request và onNext

Hãy xem nhu cầu còn lại như một bộ đếm. Mỗi lần request(n) với n dương sẽ cộng thêm n vào nhu cầu chưa được đáp ứng. Mỗi lần publisher phát một onNext hợp lệ, nhu cầu còn lại giảm đi một nếu nó đang hữu hạn.

Ví dụ:

| Thời điểm | Thao tác | Nhu cầu còn lại |
|---|---|---:|
| Bắt đầu | Chưa yêu cầu phần tử | 0 |
| 1 | request(3) | 3 |
| 2 | onNext(A) | 2 |
| 3 | onNext(B) | 1 |
| 4 | request(2) | 3 |
| 5 | onNext(C) | 2 |
| 6 | onNext(D) | 1 |
| 7 | onNext(E) | 0 |

Sau bước 7, publisher không được phát phần tử tiếp theo cho đến khi nhận thêm request. Bảng mô tả nhu cầu của một subscription; các phần tử A, B, C, D và E chỉ là dữ liệu minh họa.

Có thể biểu diễn quy tắc bằng công thức khái quát:

    nhu_cau_con_lai = tong_nhu_cau_da_yeu_cau - so_onNext_da_phat

Trong triển khai thực tế, phép cộng nhu cầu phải tránh tràn số. Reactive Streams quy định nhu cầu tích lũy được bão hòa ở Long.MAX_VALUE thay vì quay vòng thành số âm. Khi nhu cầu đạt Long.MAX_VALUE, publisher có thể xem đó là nhu cầu không giới hạn.

Mỗi request(n) phải có n lớn hơn 0. Request bằng 0 hoặc số âm là yêu cầu không hợp lệ; publisher phải kết thúc subscription bằng onError với IllegalArgumentException theo hợp đồng. Ở phía ứng dụng, hãy bảo đảm giá trị yêu cầu luôn dương và kiểm tra phép tính trước khi truyền số lượng vào request.

## 3. Số lượng yêu cầu không đồng nghĩa số lượng chắc chắn được phát

Publisher bị giới hạn bởi nhu cầu, nhưng không bị buộc phải sử dụng hết nhu cầu. Hãy phân biệt ba đại lượng:

- **Số lượng yêu cầu:** tổng các phần tử subscriber đã yêu cầu.
- **Số lượng đã phát:** số lần publisher đã gọi onNext.
- **Nhu cầu còn lại:** phần yêu cầu chưa được đáp ứng.

Ví dụ, subscriber yêu cầu năm phần tử nhưng nguồn chỉ có hai phần tử. Publisher phát hai onNext rồi onComplete. Nhu cầu còn lại không được chuyển thành hai phần tử giả và cũng không khiến publisher phải chờ nguồn phát thêm.

Tương tự, nếu nguồn gặp lỗi sau khi phát hai phần tử, publisher gửi onError và kết thúc. Nó không phải phát nốt các phần tử còn thiếu để đáp ứng số lượng đã yêu cầu.

Một vài tình huống điển hình:

| Nguồn và nhu cầu | Tín hiệu có thể quan sát | Giải thích |
|---|---|---|
| Yêu cầu 3, nguồn có ít nhất 3 phần tử | 3 lần onNext nếu nguồn tiếp tục phát, sau đó có thể còn dữ liệu | Nhu cầu cho phép tối đa 3 phần tử |
| Yêu cầu 5, nguồn chỉ có 2 phần tử | 2 lần onNext rồi onComplete | Nguồn kết thúc sớm |
| Yêu cầu 0, nguồn rỗng | onComplete sau onSubscribe | Tín hiệu kết thúc không cần nhu cầu |
| Yêu cầu 2, nguồn lỗi trước khi phát | onError sau onSubscribe | Lỗi kết thúc luồng, không cần tiêu thụ nhu cầu |
| Yêu cầu 2, nguồn có nhiều dữ liệu | Tối đa 2 lần onNext cho đến khi có request mới | Phần tử tiếp theo phải chờ nhu cầu |

Với Mono, nguồn phát tối đa một phần tử. request(1) đủ để cho phép phần tử đó được phát; nếu Mono rỗng thì subscriber chỉ nhận onComplete. Với Flux, số phần tử có thể lớn hơn một, vì vậy việc quản lý nhu cầu và bổ sung request thường ảnh hưởng rõ rệt đến thông lượng.

## 4. Tích lũy request và nhu cầu không giới hạn

Nhiều lần gọi request được cộng dồn. Nếu subscriber lần lượt gọi request(2), request(3) trước khi publisher phát dữ liệu, nhu cầu tổng cộng là năm phần tử. Publisher không cần chờ mỗi request được đáp ứng xong mới nhận request tiếp theo.

Sơ đồ sau minh họa cách nhu cầu tích lũy và được tiêu thụ:

    request(2) ----+
                  +----> Nhu cầu còn lại: 5
    request(3) ----+             |
                                 | onNext(item-1)
                                 v
                          Nhu cầu còn lại: 4
                                 |
                                 | onNext(item-2)
                                 v
                          Nhu cầu còn lại: 3
                                 |
                              ...

request(Long.MAX_VALUE) là cách yêu cầu không giới hạn. Đây là giá trị hữu ích khi subscriber có thể xử lý dữ liệu theo tốc độ của publisher hoặc khi không cần điều tiết thủ công. Tuy vậy, nó loại bỏ giới hạn nhu cầu ở subscription đó; nếu downstream chậm, các thành phần trung gian vẫn có thể phải giữ dữ liệu hoặc tiêu tốn tài nguyên.

Nhu cầu không giới hạn cũng không có nghĩa nguồn nhất thiết phát vô hạn. Publisher vẫn có thể hoàn tất, báo lỗi hoặc bị hủy. Giá trị này chỉ nói rằng subscriber không đặt giới hạn số phần tử được phép phát.

## 5. Subscriber yêu cầu theo từng đợt

Một cách điều tiết đơn giản là yêu cầu một lượng phần tử ban đầu, xử lý chúng rồi yêu cầu thêm. Ví dụ, consumer yêu cầu hai phần tử mỗi đợt. Khi xử lý xong một đợt, nó bổ sung nhu cầu cho đợt kế tiếp.

Trong Reactor, BaseSubscriber cho phép tùy chỉnh thời điểm gọi request:

    import org.reactivestreams.Subscription;
    import reactor.core.publisher.BaseSubscriber;
    import reactor.core.publisher.Flux;

    public class BatchDemandExample {
        public static void main(String[] args) {
            Flux.range(1, 5).subscribe(new BaseSubscriber<Integer>() {
                @Override
                protected void hookOnSubscribe(Subscription subscription) {
                    System.out.println("Đăng ký; yêu cầu 2 phần tử");
                    request(2);
                }

                @Override
                protected void hookOnNext(Integer value) {
                    System.out.println("Nhận: " + value);

                    if (value % 2 == 0) {
                        System.out.println("Bổ sung nhu cầu: 2 phần tử");
                        request(2);
                    }
                }

                @Override
                protected void hookOnComplete() {
                    System.out.println("Nguồn đã hoàn tất");
                }

                @Override
                protected void hookOnError(Throwable error) {
                    System.err.println("Lỗi: " + error.getMessage());
                }
            });
        }
    }

Với nguồn Flux.range(1, 5), subscriber ban đầu yêu cầu hai phần tử. Sau khi nhận phần tử thứ hai, nó yêu cầu thêm hai; sau phần tử thứ tư, nó yêu cầu thêm hai lần nữa. Nguồn chỉ còn một phần tử ở đợt cuối, nên publisher phát phần tử thứ năm rồi hoàn tất.

Kết quả minh họa:

    Đăng ký; yêu cầu 2 phần tử
    Nhận: 1
    Nhận: 2
    Bổ sung nhu cầu: 2 phần tử
    Nhận: 3
    Nhận: 4
    Bổ sung nhu cầu: 2 phần tử
    Nhận: 5
    Nguồn đã hoàn tất

Nếu subscriber chỉ yêu cầu hai phần tử và không bao giờ bổ sung nhu cầu, publisher có thể phát hai phần tử rồi tạm dừng. Subscription vẫn còn hoạt động; nó chưa hoàn tất vì nguồn chưa thể phát phần tử tiếp theo và cũng chưa gửi tín hiệu kết thúc. Ứng dụng phải quyết định khi nào yêu cầu tiếp, hủy subscription hoặc áp dụng một chính sách timeout phù hợp.

## 6. Quan hệ giữa nhu cầu downstream và upstream trong Reactor

Trong một pipeline có nhiều toán tử, subscriber cuối cùng không nhất thiết gọi request trực tiếp lên nguồn gốc. Mỗi toán tử trung gian nhận nhu cầu từ downstream, rồi quyết định cách yêu cầu dữ liệu upstream để thực hiện công việc của mình.

Ví dụ:

    Flux.range(1, 100)
        .filter(value -> value % 2 == 0)
        .map(value -> value * 10)
        .subscribe(value -> process(value));

Subscriber cuối nhận các giá trị đã lọc và biến đổi. Một yêu cầu một phần tử ở downstream không nhất thiết chỉ làm nguồn range phát đúng một phần tử, bởi filter có thể phải kiểm tra nhiều phần tử upstream mới tìm được một giá trị phù hợp. Toán tử filter có thể yêu cầu thêm dữ liệu để bù cho các phần tử bị loại bỏ, trong khi vẫn bảo đảm số phần tử phát ra downstream không vượt quá nhu cầu downstream.

Điều này cho thấy nhu cầu được phối hợp qua pipeline chứ không phải một con số đơn giản được sao chép nguyên vẹn qua mọi toán tử. Các toán tử như buffer có thể gom nhiều phần tử thành một nhóm; flatMap có thể theo dõi nhiều inner publisher đồng thời; publishOn có thể dùng hàng đợi và prefetch để tách nhịp giữa hai scheduler.

### 6.1. Prefetch và lượng dữ liệu được yêu cầu trước

Một số toán tử chủ động yêu cầu trước một lượng dữ liệu để cải thiện thông lượng. Lượng yêu cầu trước này thường được gọi là prefetch. Nó giúp downstream không phải chờ từng phần tử mới bắt đầu xử lý phần tiếp theo, nhưng cũng có nghĩa dữ liệu có thể được giữ trong hàng đợi nội bộ.

Ví dụ, flatMap có thể xử lý nhiều inner publisher đồng thời và mỗi inner publisher có một mức prefetch. Tăng concurrency hoặc prefetch có thể cải thiện thông lượng khi downstream đủ năng lực, nhưng cũng có thể tăng lượng dữ liệu đang chờ và áp lực bộ nhớ.

Vì vậy, khi điều chỉnh pipeline, cần xem xét cùng lúc:

- Nhu cầu subscriber cuối cùng.
- Mức prefetch của các toán tử trung gian.
- Số inner publisher được xử lý đồng thời.
- Dung lượng hàng đợi hoặc buffer.
- Tốc độ và giới hạn của dịch vụ downstream.

Không nên kết luận rằng request(1) ở subscriber luôn đồng nghĩa chỉ có một phần tử tồn tại trong toàn bộ pipeline. Nó giới hạn phần tử phát đến subscription ở ranh giới đó; các toán tử trung gian có thể có dữ liệu đã yêu cầu trước và đang giữ trong bộ đệm.

## 7. Backpressure bảo vệ hệ thống như thế nào?

Giả sử một nguồn phát một nghìn phần tử mỗi giây, trong khi consumer chỉ xử lý được một trăm phần tử mỗi giây. Nếu hệ thống không điều tiết, chênh lệch tốc độ sẽ làm công việc tồn đọng tăng dần. Một hàng đợi không giới hạn có thể tiêu thụ hết bộ nhớ; hàng đợi có giới hạn cuối cùng phải từ chối, chặn, bỏ hoặc chuyển dữ liệu đi nơi khác.

Backpressure cho phép consumer biểu thị lượng dữ liệu mà nó có thể nhận. Với nguồn Reactive Streams tuân thủ hợp đồng, publisher không phát onNext vượt quá nhu cầu còn lại. Khi consumer chậm và chưa yêu cầu thêm, publisher phải giảm hoặc dừng việc phát ở ranh giới subscription đó.

Tuy nhiên, backpressure không tự giải quyết mọi trường hợp:

- Nó điều tiết số phần tử, không trực tiếp điều tiết số byte. Một phần tử rất lớn vẫn có thể chiếm nhiều bộ nhớ.
- Nguồn bên ngoài như callback API, socket adapter hoặc thiết bị cảm biến có thể không hỗ trợ tạm dừng. Adapter phải chọn cách buffer, drop, giữ giá trị mới nhất hoặc báo lỗi.
- Các toán tử có prefetch hoặc buffer có thể giữ dữ liệu đã được yêu cầu trước.
- Nếu subscriber yêu cầu không giới hạn, nó đã chủ động bỏ giới hạn nhu cầu tại subscription đó.

Với nguồn không thể tạm dừng, hãy chọn chính sách phù hợp với ý nghĩa dữ liệu. Sự kiện thanh toán hoặc thay đổi trạng thái đơn hàng thường không thể tùy tiện bỏ. Luồng cập nhật vị trí hoặc số liệu hiển thị có thể chỉ cần giá trị mới nhất. Buffer có giới hạn phù hợp khi có thể hấp thụ một đợt tải ngắn và có hành vi rõ ràng khi đầy.

## 8. Kiểm thử quan hệ request và onNext bằng StepVerifier

StepVerifier cho phép đặt nhu cầu ban đầu và bổ sung request theo từng bước. Cách này giúp xác minh publisher không phát vượt quá số phần tử đã yêu cầu.

Ví dụ, bắt đầu với nhu cầu bằng không, sau đó yêu cầu lần lượt hai, hai và một phần tử:

    import reactor.core.publisher.Flux;
    import reactor.test.StepVerifier;

    StepVerifier.create(Flux.range(1, 5), 0)
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(2)
        .expectNext(3, 4)
        .thenRequest(1)
        .expectNext(5)
        .verifyComplete();

Ở đây:

1. Initial request bằng 0 nên verifier chưa yêu cầu phần tử nào.
2. thenRequest(2) cho phép publisher phát hai phần tử.
3. Sau khi xác nhận hai phần tử đầu, verifier yêu cầu thêm hai.
4. Cuối cùng, verifier yêu cầu một phần tử và xác nhận phần tử thứ năm.
5. verifyComplete xác nhận nguồn kết thúc bình thường sau khi phát đủ dữ liệu.

Có thể kiểm tra một nguồn ngắn hơn nhu cầu. Subscriber yêu cầu năm phần tử nhưng nguồn chỉ có hai:

    StepVerifier.create(Flux.just("A", "B"), 0)
        .expectSubscription()
        .thenRequest(5)
        .expectNext("A", "B")
        .verifyComplete();

Publisher phát hai phần tử rồi hoàn tất. Không có lỗi vì nguồn không cần đáp ứng đủ số lượng yêu cầu.

## 9. Những lỗi thường gặp khi làm việc với request

**Cho rằng request(n) là số phần tử publisher bắt buộc phải phát.** Đây là mức tối đa được phép phát theo nhu cầu hiện tại. Nguồn có thể kết thúc sớm hoặc báo lỗi.

**Quên rằng nhiều request được cộng dồn.** request(2) rồi request(3) tạo nhu cầu tổng cộng năm phần tử nếu chưa có onNext tiêu thụ nhu cầu.

**Gọi request(0) để tạm dừng.** Giá trị không dương không phải lệnh tạm dừng; nó là yêu cầu không hợp lệ và dẫn đến onError. Để tạm dừng, subscriber chỉ cần không yêu cầu thêm phần tử.

**Không bổ sung nhu cầu sau khi đã tiêu thụ hết.** Publisher sẽ dừng phát onNext khi nhu cầu hữu hạn về không. Nếu subscriber muốn tiếp tục, nó phải gọi request thêm.

**Đồng nhất nhu cầu downstream với dung lượng toàn pipeline.** Toán tử trung gian có thể prefetch và buffer dữ liệu. Cần xem xét hàng đợi nội bộ và concurrency khi ước lượng bộ nhớ.

**Dùng nhu cầu không giới hạn cho mọi nguồn.** Long.MAX_VALUE thuận tiện nhưng không tạo ra cơ chế bảo vệ khi consumer chậm. Chỉ sử dụng khi ứng dụng có thể chấp nhận cách tiêu thụ đó.

## 10. Checklist đọc một pipeline theo nhu cầu

Khi phân tích một pipeline Reactive Streams, hãy xác định:

1. Subscription nào đang được điều khiển và subscriber nào sở hữu nó?
2. Nhu cầu ban đầu là bao nhiêu: bằng không, hữu hạn hay không giới hạn?
3. Những nơi nào gọi request bổ sung, và mỗi lần yêu cầu bao nhiêu?
4. Có bao nhiêu onNext đã được phát tại ranh giới subscriber đang quan sát?
5. Toán tử nào lọc, gom nhóm, prefetch hoặc tạo nhiều luồng con?
6. Khi nhu cầu về không, pipeline sẽ chờ, buffer, drop hay kết thúc?
7. Nguồn có thật sự hỗ trợ backpressure, hay adapter cần một chính sách riêng?

Khi trả lời được các câu hỏi này, ta có thể dự đoán số phần tử tối đa được phát đến từng subscriber, giải thích vì sao pipeline tạm dừng và chọn cách điều tiết phù hợp. Quan hệ giữa request và onNext chính là cơ chế định lượng giúp Reactive Streams phối hợp tốc độ giữa bên sản xuất và bên tiêu thụ trong một hệ thống bất đồng bộ.
