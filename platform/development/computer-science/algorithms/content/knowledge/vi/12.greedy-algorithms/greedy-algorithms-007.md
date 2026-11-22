# Lập lịch để giảm độ trễ lớn nhất

Trong một hệ thống có nhiều công việc cần thực hiện trên **một máy duy nhất**, mỗi công việc có thời lượng xử lý và hạn hoàn thành. Nếu thực hiện một công việc quá muộn, công việc đó có thể vượt quá hạn chót. Câu hỏi là: **nên xếp các công việc theo thứ tự nào để độ trễ lớn nhất của cả lịch là nhỏ nhất?**

Đây là một bài toán tiêu biểu của **thuật toán tham lam (greedy algorithms)**. Trong mô hình cơ bản, quy tắc tối ưu rất ngắn: **xếp công việc theo hạn hoàn thành tăng dần — Earliest Due Date (EDD)**. Điều đáng học không chỉ là nhớ quy tắc EDD, mà là hiểu chính xác mô hình áp dụng, phân biệt độ trễ có dấu với độ quá hạn, và chứng minh vì sao đổi chỗ hai công việc sai thứ tự không làm mục tiêu xấu đi.

Bài học nằm trong nhóm **Tham lam** của Computer Science Algorithms; bao gồm đặc tả, ví dụ, giả mã, lập luận đổi chỗ kề nhau, hiện thực Java 17+, kiểm thử bằng vét cạn, những mô hình mà EDD không còn tự động đúng và bài tập vận dụng.

## 1. Đặc tả một máy, tất cả công việc sẵn sàng tại thời điểm 0

Cho n công việc J1, J2, ..., Jn. Mỗi công việc i có:

- **p_i:** thời gian xử lý (processing time), p_i ≥ 0.
- **d_i:** hạn mong muốn hoàn thành (due date/deadline), có thể là số nguyên âm, 0 hoặc dương theo cùng mốc thời gian.
- **id_i:** mã nhận dạng công việc để trả lại thứ tự theo dữ liệu gốc.

Giả thiết cơ bản:

1. Có **một máy** và mỗi thời điểm chỉ thực hiện nhiều nhất một công việc.
2. Tất cả công việc **đã sẵn sàng tại thời điểm 0**; không có release time r_i khác nhau.
3. Một công việc khi bắt đầu sẽ chạy liên tục tới hết; **không ngắt để làm việc khác** (non-preemptive).
4. Không có thời gian chuyển đổi/cài đặt phụ thuộc thứ tự, không có ràng buộc công việc trước–sau.
5. Mọi công việc đều phải được xử lý; không được bỏ công việc có hạn khó đạt.
6. Mục tiêu là **giảm giá trị lớn nhất của độ trễ hoàn thành có dấu** trong toàn bộ lịch.

Với các giả thiết này, một lịch không có khoảng rỗi giữa các công việc là đủ để đạt tối ưu: nếu tất cả việc đều sẵn sàng thì xóa một khoảng rỗi chỉ giúp công việc phía sau kết thúc sớm hơn hoặc không đổi, không làm tăng độ trễ của công việc nào.

Đây chính là lớp bài toán lập lịch một máy tối thiểu hóa **maximum lateness**, thường ký hiệu **1||L_max** trong ký pháp scheduling. Nếu thay đổi giả thiết, cần chứng minh lại quy tắc chứ không mặc nhiên dùng EDD.

## 2. Độ trễ L_i khác độ quá hạn T_i

Với lịch cố định, công việc i bắt đầu tại S_i, hoàn tất ở C_i = S_i + p_i. Đặt:

~~~text
L_i = C_i - d_i                 (lateness: độ trễ có dấu)
T_i = max(0, C_i - d_i)         (tardiness: phần quá hạn, luôn không âm)
L_max = max_i L_i
T_max = max_i T_i = max(0, L_max), với n > 0.
~~~

**Lateness có thể âm.** L_i = −7 nghĩa là công việc hoàn thành sớm hơn hạn 7 đơn vị thời gian; L_i = 0 nghĩa là vừa đúng hạn; L_i = 4 nghĩa là muộn 4 đơn vị. Tardiness không mang phần âm: hoàn thành trước hạn thì T_i = 0.

Chúng là hai chỉ số khác nhau, nhưng khi tối ưu **giá trị lớn nhất** trên cùng tập lịch, EDD cũng tối ưu T_max, bởi hàm x → max(0,x) là không giảm. Điều đó **không có nghĩa** EDD luôn tối ưu tổng số đơn vị quá hạn, tổng thời gian hoàn thành, số việc quá hạn hoặc mục tiêu có trọng số.

**Trường hợp không có công việc:** về toán học, max của tập độ trễ rỗng không có giá trị số thông thường. Chương trình trong bài quy ước **trả 0** cho L_max của lịch rỗng để API dễ sử dụng; đây là quy ước tường minh, không phải một định lý rằng max của tập rỗng bằng 0.

## 3. Tính độ trễ của một thứ tự cụ thể

Giả sử máy bắt đầu hoạt động tại thời điểm 0, không có thời gian rỗi. Với thứ tự công việc π = [π1, π2, ..., πn]:

~~~text
C(π1) = p(π1)
C(π2) = p(π1) + p(π2)
...
C(πk) = tổng p(πj) với j từ 1 tới k

L(πk) = C(πk) - d(πk)
L_max(π) = max các L(πk).
~~~

Mục tiêu là tìm hoán vị π sao cho **L_max(π) là nhỏ nhất**. Chú ý giá trị tối ưu có thể âm: nếu mọi công việc đều hoàn tất sớm, độ trễ lớn nhất vẫn là một số âm.

Một cách thử trực tiếp là liệt kê tất cả n! hoán vị, tính L_max từng lịch và lấy giá trị nhỏ nhất. Cách đó giúp xây dựng *oracle* kiểm thử với n nhỏ, nhưng n! tăng quá nhanh để dùng cho đầu vào lớn.

Khi phân tích phải phân biệt **giá trị kết quả** (một số) với **lịch tối ưu** (thứ tự ID). Bài toán yêu cầu lập lịch nên một hiện thực hữu ích nên cung cấp cả thứ tự lẫn L_max, không chỉ công bố giá trị nhỏ nhất.

## 4. Quy tắc tham lam EDD (Earliest Due Date)

**Chiến lược:** sắp xếp tất cả công việc theo d_i tăng dần, sau đó xử lý tuần tự theo thứ tự này từ thời điểm 0, không cố ý chờ.

Giả mã:

~~~text
EDD(jobs):
    kiểm tra đầu vào và các tiền điều kiện
    sắp jobs theo (deadline tăng dần, ID tăng dần khi cùng deadline)
    completion = 0
    maximumLateness = -vô_cùng

    với từng job trong thứ tự đã sắp:
        completion = completion + job.processing
        lateness = completion - job.deadline
        maximumLateness = max(maximumLateness, lateness)

    trả về (thứ tự công việc, maximumLateness)
~~~

Sắp theo ID khi d_i bằng nhau **chỉ để kết quả xác định**, không phải điều kiện để đạt tối ưu. Với các công việc cùng hạn d, tổng thời gian của nhóm không đổi, nên max lateness của nhóm vẫn phụ thuộc vào thời điểm hoàn tất **công việc cuối cùng trong nhóm**, bất kể thứ tự nội bộ (nếu p ≥ 0).

**Điểm quan trọng:** EDD dựa trên hạn d_i, **không dựa trên p_i**. Không phải lúc nào việc ngắn hơn cũng phải được làm trước. Ưu tiên thời lượng ngắn nhất (SPT) là một quy tắc khác, thường gắn với mục tiêu tổng thời gian hoàn thành chứ không bảo đảm tối ưu L_max.

## 5. Ví dụ: EDD so với ưu tiên việc ngắn nhất

Xét bốn công việc:

| ID | Thời lượng p | Hạn d |
| --- | ---: | ---: |
| 1 | 4 | 4 |
| 2 | 1 | 100 |
| 3 | 3 | 6 |
| 4 | 2 | 7 |

EDD sắp theo hạn **[1, 3, 4, 2]**. Không chèn thời gian rỗi:

| Thứ tự EDD | p | d | Thời điểm C hoàn tất | L = C−d |
| --- | ---: | ---: | ---: | ---: |
| 1 | 4 | 4 | 4 | 0 |
| 3 | 3 | 6 | 7 | 1 |
| 4 | 2 | 7 | 9 | 2 |
| 2 | 1 | 100 | 10 | −90 |

Vậy **L_max(EDD) = 2**. Công việc 4 trễ nhiều nhất 2 đơn vị; công việc 2 hoàn thành trước hạn tới 90 đơn vị.

Nếu dùng SPT, thứ tự là **[2, 4, 3, 1]**:

| Thứ tự SPT | p | d | C | L = C−d |
| --- | ---: | ---: | ---: | ---: |
| 2 | 1 | 100 | 1 | −99 |
| 4 | 2 | 7 | 3 | −4 |
| 3 | 3 | 6 | 6 | 0 |
| 1 | 4 | 4 | 10 | 6 |

**L_max(SPT) = 6**, lớn hơn 2. Đây là phản ví dụ trực tiếp cho lời khẳng định “việc ngắn nhất trước luôn giảm độ trễ lớn nhất”.

Nếu tất cả công việc đều hoàn thành trước hạn, chẳng hạn công việc p=2 và p=1 cùng hạn 10, EDD kết thúc tại 2 và 3, có L bằng −8 và −7, nên **L_max = −7**, nhưng **T_max = 0**. Đó không phải mâu thuẫn: hai chỉ số có định nghĩa khác nhau.

## 6. Bất biến của lịch EDD sau khi sắp xếp

Sau khi sắp công việc, ta có:

~~~text
d(π1) <= d(π2) <= ... <= d(πn).
~~~

Trong vòng lặp xây dựng lịch:

- completion là tổng thời gian xử lý của tất cả công việc đã đi qua.
- maximumLateness là giá trị lớn nhất của C_i − d_i trong **các công việc đã được xử lý**.
- Danh sách công việc đã xử lý là một tiền tố của thứ tự deadline không giảm.
- Nếu chưa xử lý công việc nào, completion = 0; maximumLateness khởi tạo bằng Long.MIN_VALUE và chỉ được dùng với lịch không rỗng.

Mỗi lượt cộng p_i vào completion, tính đúng thời điểm hoàn tất của công việc hiện tại rồi cập nhật maximumLateness. Sau n lượt, biến lưu max của toàn bộ n giá trị L_i. Đây là **bất biến tính toán của chương trình**, giúp chứng minh giá trị của lịch đã tạo được tính chính xác.

Tuy nhiên, biết chương trình tính đúng L_max của lịch EDD **chưa đủ** để nói lịch EDD tối ưu so với mọi hoán vị. Cần thêm lập luận tham lam dựa trên đổi chỗ.

## 7. Chứng minh tối ưu bằng phép đổi chỗ hai công việc kề nhau

Xét một lịch không có thời gian rỗi với hai công việc **i rồi j** đứng kề nhau, nhưng bị **ngược thứ tự hạn**: d_i > d_j. Gọi t là thời điểm bắt đầu công việc i, với thời lượng p_i, p_j ≥ 0.

**Trước khi đổi** thứ tự i, j:

~~~text
C_i = t + p_i
L_i = t + p_i - d_i

C_j = t + p_i + p_j
L_j = t + p_i + p_j - d_j
~~~

Vì p_j ≥ 0 và d_i > d_j, ta có **L_j ≥ L_i**. Như vậy độ trễ lớn nhất của **cặp cũ** bằng L_j.

**Sau khi đổi** thứ tự thành j, i:

~~~text
C'_j = t + p_j
L'_j = t + p_j - d_j
     <= t + p_i + p_j - d_j = L_j

C'_i = t + p_j + p_i
L'_i = t + p_i + p_j - d_i
     <= t + p_i + p_j - d_j = L_j
~~~

Cả hai độ trễ sau đổi đều **không vượt độ trễ L_j của cặp trước đổi**. Các công việc **đứng trước** cặp không đổi, và các công việc **đứng sau** cặp bắt đầu đúng cùng thời điểm như trước vì tổng p_i + p_j không đổi. Do đó **L_max của toàn lịch không tăng** khi đổi một cặp kề nhau bị ngược deadline.

Bất kỳ thứ tự công việc nào cũng có thể được chuyển thành thứ tự deadline không giảm bằng một chuỗi hữu hạn các phép đổi cặp kề nhau bị ngược (tương tự quá trình bubble sort). Mỗi phép đổi không làm L_max tăng. Vì thế, **từ một lịch tối ưu bất kỳ, có thể tạo lịch EDD có L_max không lớn hơn tối ưu; do đó EDD cũng tối ưu.**

Đây là **exchange argument** tiêu biểu của thuật toán tham lam: chứng minh một lựa chọn theo quy tắc tham lam có thể đưa vào một nghiệm tối ưu mà không làm nghiệm kém đi, rồi lặp lại.

## 8. Vì sao được bỏ mọi thời gian chờ cố ý?

Lập luận đổi chỗ ở trên xét lịch xử lý liên tục, không có khoảng rỗi. Điều đó là hợp lệ nhờ giả thiết **mọi việc sẵn sàng từ thời điểm 0**.

Giả sử một lịch có khoảng máy rỗi trước một hoặc nhiều công việc. Dịch chuyển những công việc phía sau về sớm hơn mà vẫn giữ nguyên thứ tự, xóa khoảng rỗi đó. Vì không có release time hay ràng buộc trước–sau, tất cả công việc được dịch vẫn thực hiện hợp lệ. Thời điểm hoàn thành C_i của chúng **không tăng**, nên từng L_i = C_i−d_i cũng không tăng; max của chúng không tăng.

Lặp lại với mọi khoảng rỗi sẽ cho một lịch không chờ có L_max không lớn hơn lịch ban đầu. Vậy tồn tại **ít nhất một lịch tối ưu không có thời gian rỗi cố ý**, đủ để áp dụng chứng minh đổi chỗ.

**Khi có release time:** dịch một công việc về trước thời điểm nó sẵn sàng có thể làm lịch vô hiệu. Khi đó lập luận này hỏng, và EDD không còn là đáp án tối ưu tổng quát của bài toán mở rộng.

## 9. Ràng buộc áp dụng, trường hợp hòa và dữ liệu bất thường

Bài toán thực tế cần xác nhận từng giả thiết trước khi dùng EDD:

| Yếu tố | Bài toán EDD chuẩn trong bài | Nếu thay đổi |
| --- | --- | --- |
| Số máy | Một | Nhiều máy cần mô hình riêng |
| Thời điểm sẵn sàng | Tất cả từ t = 0 | Release time có thể làm phải chờ, có thể phá tối ưu EDD |
| Ngắt việc | Không ngắt | Preemption làm không gian lịch khác đi |
| Độ dài xử lý | p ≥ 0 | p âm vô nghĩa trong mô hình thời lượng |
| Hạn công việc | Deadline d, có thể trùng hoặc âm | Dữ liệu cần dùng cùng hệ quy chiếu thời gian |
| Ràng buộc trước–sau | Không có | Có precedence thì không thể tự ý đổi thứ tự |
| Chi phí setup | Không có | Setup phụ thuộc thứ tự làm tổng thời gian thay đổi khi đổi chỗ |
| Mục tiêu | Min L_max, hoặc tương đương min T_max | Min tổng tardiness, số việc trễ, chi phí có trọng số là bài khác |

**Deadline trùng:** nếu hai công việc có cùng d, chọn thứ tự bất kỳ giữa chúng không đổi max độ trễ của cặp khi mọi p ≥ 0 và hai việc liên tiếp. Chương trình xếp theo ID tăng dần để dễ kiểm thử và tái hiện.

**Deadline âm:** công việc có hạn trước thời điểm 0 có thể luôn trễ; công thức và chứng minh EDD vẫn đúng nếu số học biểu diễn được. Không được suy diễn rằng deadline âm là đầu vào không hợp lệ trừ khi đề bài quy định như vậy.

**p = 0:** công việc độ dài 0 không làm thời điểm hoàn thành tăng, vẫn có thể có độ trễ; phép chứng minh đổi chỗ dùng p ≥ 0 nên chấp nhận trường hợp 0. Nếu ứng dụng thực tế không muốn các công việc không thời lượng, có thể siết đầu vào p > 0.

## 10. Phản ví dụ khi có thời điểm phát hành công việc

Xét hai công việc và một máy:

- A: sẵn sàng lúc **r_A=0**, p_A=5, d_A=100.
- B: sẵn sàng lúc **r_B=1**, p_B=1, d_B=2.

Nếu tại t=0 bắt đầu ngay công việc A (vì B chưa sẵn sàng), thì A kết thúc lúc 5, B chạy từ 5 tới 6 và trễ **6−2=4**. L_max của lịch này là 4.

Nếu máy **cố ý chờ tới t=1**, làm B trong [1,2) rồi A trong [2,7), ta có L_B=0 và L_A=7−100=−93, nên **L_max=0**, tốt hơn.

Ở đây ta không thể làm B ngay tại thời điểm 0 theo thứ tự EDD của danh sách gốc vì B chưa sẵn sàng. Đồng thời, việc loại bỏ thời gian rỗi từ lịch thứ hai làm B vi phạm release time. Vì vậy chứng minh EDD của mô hình chuẩn **không được chuyển nguyên xi** sang bài toán có release dates.

Phản ví dụ này không nói mọi biến thể EDD đều vô ích với release times; nó nói **một quy tắc EDD tĩnh, không ngắt và không xét quyết định chờ không có bảo đảm tối ưu L_max trong mô hình mở rộng**.

## 11. Độ phức tạp của thuật toán và chi phí khôi phục lịch

Đối với n công việc:

1. Sao chép mảng Job[] để giữ nguyên thứ tự đầu vào: O(n) thời gian và O(n) bộ nhớ cho mảng tham chiếu.
2. Kiểm tra null, p ≥ 0 và ID phân biệt: O(n) thời gian trung bình với HashSet và O(n) bộ nhớ thêm.
3. Sắp xếp theo deadline rồi ID: O(n log n) thời gian ở trường hợp tổng quát; bộ nhớ phụ tùy hiện thực sorting của thư viện.
4. Duyệt tính completion, lateness và L_max: O(n) thời gian, O(1) biến phụ.
5. Trả lại danh sách theo thứ tự tối ưu và giá trị L_max: không cần tìm kiếm ngược vì ta đã giữ nguyên từng đối tượng Job cùng ID.

Do đó thời gian tổng thể là **O(n log n)** và bộ nhớ phụ của chương trình là **O(n)** cho bản sao mảng, HashSet và bộ nhớ sắp xếp (không tính đối tượng Job đầu vào đã tồn tại).

Nếu chỉ cần giá trị L_max mà không cần bảo toàn thứ tự đầu vào, có thể sắp xếp trực tiếp mảng thay vì clone, nhưng đó là **một hợp đồng tác động phụ khác**. Trong lập lịch thực tế, trả lại ID của các công việc thường quan trọng hơn việc chỉ in độ trễ.

Bộ kiểm thử vét cạn ở phần Java là công cụ xác minh **riêng**, có thời gian giai thừa theo n; không được tính nó vào O(n log n) của thuật toán EDD khi triển khai thật.

## 12. Java 17+ hoàn chỉnh: lịch EDD và kiểm thử vét cạn

Chương trình dùng hai record của Java: Job(id, processing, deadline) và Result(order, maximumLateness). Hàm schedule:

- Từ chối input null, job null, thời lượng âm và ID trùng.
- **Clone** mảng đầu vào, không đổi thứ tự mà người gọi đang giữ.
- Sắp xếp theo deadline tăng dần, hòa thì theo ID tăng dần.
- Tính thời điểm hoàn tất và độ trễ với long, dùng Math.addExact và Math.subtractExact để **phát hiện tràn số** thay vì âm thầm cho kết quả wrap.
- Trả mảng Job[] theo thứ tự EDD và giá trị L_max; với mảng rỗng trả 0 theo quy ước API đã nêu.

**Giới hạn số học:** các phép cộng thời lượng và trừ deadline phải nằm trong miền long, nếu không Math.addExact/Math.subtractExact sẽ ném ArithmeticException. Số liệu thật có thời gian cực lớn cần xử lý theo chính sách riêng, hoặc dùng BigInteger. Hàm Result lưu mảng Job[] có thể bị thay đổi qua accessor; ví dụ này giả định người gọi **không chỉnh sửa mảng kết quả**. API sản xuất có thể trả bản sao phòng vệ hoặc danh sách bất biến.

Lưu tệp **MaximumLatenessEDD.java**:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;

public final class MaximumLatenessEDD {
    public record Job(int id, long processing, long deadline) { }
    public record Result(Job[] order, long maximumLateness) { }

    private MaximumLatenessEDD() { }

    public static Result schedule(Job[] input) {
        if (input == null) {
            throw new IllegalArgumentException("jobs must not be null");
        }

        Job[] jobs = input.clone();
        Set<Integer> ids = new HashSet<>();
        for (Job job : jobs) {
            if (job == null || job.processing() < 0
                    || !ids.add(job.id())) {
                throw new IllegalArgumentException(
                    "non-null jobs, unique IDs and nonnegative times required"
                );
            }
        }

        Arrays.sort(jobs,
            Comparator.comparingLong(Job::deadline)
                .thenComparingInt(Job::id));

        return new Result(jobs, evaluate(jobs));
    }

    private static long evaluate(Job[] order) {
        if (order.length == 0) {
            return 0L; /* API convention: no jobs */
        }

        long completion = 0L;
        long maximum = Long.MIN_VALUE;
        for (Job job : order) {
            completion = Math.addExact(completion, job.processing());
            long lateness = Math.subtractExact(
                completion, job.deadline()
            );
            maximum = Math.max(maximum, lateness);
        }
        return maximum;
    }

    private static void swap(Job[] a, int i, int j) {
        Job temp = a[i];
        a[i] = a[j];
        a[j] = temp;
    }

    private static long bruteOptimal(Job[] jobs) {
        if (jobs.length == 0) {
            return 0L;
        }
        return enumerate(jobs.clone(), 0);
    }

    private static long enumerate(Job[] perm, int index) {
        if (index == perm.length) {
            return evaluate(perm);
        }
        long best = Long.MAX_VALUE;
        for (int j = index; j < perm.length; j++) {
            swap(perm, index, j);
            best = Math.min(best, enumerate(perm, index + 1));
            swap(perm, index, j);
        }
        return best;
    }

    private static int[] ids(Job[] order) {
        int[] ids = new int[order.length];
        for (int i = 0; i < order.length; i++) {
            ids[i] = order[i].id();
        }
        return ids;
    }

    private static void verify() {
        long[] dueOptions = {-1L, 1L, 3L};
        int checked = 0;
        for (int n = 0; n <= 4; n++) {
            int combinations = 1;
            for (int i = 0; i < n; i++) {
                combinations *= 6;
            }
            for (int code = 0; code < combinations; code++) {
                int remaining = code;
                Job[] instance = new Job[n];
                for (int i = 0; i < n; i++) {
                    int choice = remaining % 6;
                    remaining /= 6;
                    long processing = 1L + choice % 2;
                    long deadline = dueOptions[choice / 2];
                    instance[i] = new Job(i + 1, processing, deadline);
                }
                long edd = schedule(instance).maximumLateness();
                long optimal = bruteOptimal(instance);
                if (edd != optimal) {
                    throw new AssertionError(
                        "EDD mismatch on " + Arrays.toString(instance)
                    );
                }
                checked++;
            }
        }

        Job[] edges = {
            new Job(9, 0, -2),
            new Job(4, 3, 2),
            new Job(7, 0, 2)
        };
        if (schedule(edges).maximumLateness() != bruteOptimal(edges)) {
            throw new AssertionError("Zero-duration edge case failed");
        }
        if (!Arrays.equals(ids(schedule(new Job[] {
                new Job(8, 1, 10), new Job(3, 2, 10)
            }).order()), new int[] {3, 8})) {
            throw new AssertionError("Deadline tie order failed");
        }

        System.out.println("Verified " + checked + " small instances: PASS");
        System.out.println("Additional edge cases: PASS");
    }

    public static void main(String[] args) {
        Job[] jobs = {
            new Job(1, 4, 4),
            new Job(2, 1, 100),
            new Job(3, 3, 6),
            new Job(4, 2, 7)
        };

        Result edd = schedule(jobs);
        System.out.println("EDD IDs: " + Arrays.toString(ids(edd.order())));
        System.out.println("EDD maximum lateness: " + edd.maximumLateness());

        Job[] shortest = jobs.clone();
        Arrays.sort(shortest,
            Comparator.comparingLong(Job::processing)
                .thenComparingInt(Job::id));
        System.out.println("SPT maximum lateness: " + evaluate(shortest));

        Result early = schedule(new Job[] {
            new Job(9, 1, 10),
            new Job(3, 2, 10)
        });
        System.out.println("All early maximum lateness: "
                + early.maximumLateness());
        System.out.println("All early maximum tardiness: "
                + Math.max(0L, early.maximumLateness()));
        System.out.println("Empty maximum lateness: "
                + schedule(new Job[0]).maximumLateness());

        verify();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac MaximumLatenessEDD.java
java MaximumLatenessEDD
~~~

Đầu ra đã kiểm chứng:

~~~text
EDD IDs: [1, 3, 4, 2]
EDD maximum lateness: 2
SPT maximum lateness: 6
All early maximum lateness: -7
All early maximum tardiness: 0
Empty maximum lateness: 0
Verified 1555 small instances: PASS
Additional edge cases: PASS
~~~

Ở ví dụ đầu, EDD trả ID [1,3,4,2] với L_max=2; thứ tự theo xử lý ngắn nhất trong cùng dữ liệu có L_max=6. Hai công việc cùng hạn 10 cho L_max=−7 nhưng T_max=0. Lịch rỗng trả giá trị API 0. Các dòng PASS là kết quả bộ kiểm thử được mô tả ở mục tiếp theo.

## 13. Tự kiểm thử: so sánh tham lam với lời giải hoàn toàn vét cạn

Với n nhỏ, có thể sinh **mọi hoán vị** của các công việc, tính L_max của từng lịch, rồi lấy giá trị nhỏ nhất làm **oracle**. Cách này độc lập với quy tắc EDD: nó không giả định sắp theo deadline sẽ tối ưu, mà thử toàn bộ thứ tự.

Bộ verify trong mã chọn mỗi công việc từ 6 cấu hình:

- Thời lượng p thuộc {1,2}.
- Deadline d thuộc {−1,1,3}.
- ID theo thứ tự chỉ số để bảo đảm mỗi công việc có mã khác nhau.
- Số việc n chạy từ 0 tới 4.

Tổng số bộ đầu vào được xét:

~~~text
Số cấu hình cho một công việc = 2 × 3 = 6.
Số bộ dữ liệu n=0..4 = 6^0 + 6^1 + 6^2 + 6^3 + 6^4
                      = 1 + 6 + 36 + 216 + 1296
                      = 1555.
~~~

Với mỗi trường hợp, chương trình lấy L_max của lịch EDD rồi đối chiếu với L_max **nhỏ nhất trong mọi hoán vị**, báo lỗi nếu khác nhau. Bộ tự kiểm tra còn thêm công việc p=0, hạn âm, các hạn bằng nhau và kiểm tra quy tắc xếp ID để kết quả lặp lại ổn định.

**Vì sao không duyệt vét cạn khi n lớn?** Số thứ tự có thể là n!; riêng n=10 đã có 3.628.800 hoán vị, và số này tăng rất nhanh. Oracle chỉ phục vụ kiểm thử nhỏ; chứng minh đổi chỗ mới là cơ sở khẳng định EDD tối ưu trên tất cả đầu vào hợp lệ.

Một bài kiểm thử tốt phải đối chiếu **giá trị mục tiêu tối ưu** chứ không luôn đòi EDD trùng chính xác thứ tự của một nghiệm vét cạn. Khi hạn bằng nhau có thể tồn tại nhiều lịch tối ưu với thứ tự ID khác nhau.

## 14. Các lỗi thường gặp khi giải bài toán độ trễ lớn nhất

1. **Nhầm L_max với T_max.** Nếu mọi việc xong sớm, L_max có thể âm; không tự thay giá trị âm bằng 0 trừ khi bài toán yêu cầu tardiness.
2. **Tưởng EDD tối ưu mọi mục tiêu lịch.** EDD tối ưu maximum lateness của mô hình chuẩn, không suy ra tối ưu tổng completion, tổng tardiness hoặc số công việc trễ.
3. **Nhầm deadline và thời lượng.** EDD xếp theo d tăng; SPT xếp theo p tăng và có thể cho L_max lớn hơn.
4. **Không nêu thời điểm sẵn sàng.** Với release times, một công việc đến muộn có thể khiến việc chờ hoặc ngắt công việc trở thành quyết định quan trọng.
5. **Không xét thời gian rỗi.** Trong mô hình chuẩn, idle không có lợi; trong mô hình release dates, idle đôi khi bắt buộc và có thể là tối ưu.
6. **Đổi chỗ nhưng quên công việc phía sau.** Phải giải thích tổng p của cặp giữ nguyên, nên completion của mọi công việc sau cặp không thay đổi.
7. **Chỉ chứng minh việc trễ nhất của cặp sau đổi tốt hơn một công việc trước đổi.** Cần chặn **cả hai độ trễ mới** bởi max của cặp trước đổi.
8. **Không bảo toàn danh tính.** Sắp xếp deadline tách riêng rồi chỉ trả ID từ vị trí cũ sẽ làm lệch lịch.
9. **Comparator sai:** trừ hai deadline dạng long rồi ép kết quả về int có thể tràn và gây thứ tự sai; hãy dùng Long.compare hoặc Comparator.comparingLong.
10. **Tính tổng thời lượng bằng int.** Completion có thể vượt int ngay khi mỗi p hợp lệ trong int; dùng long và xét overflow.
11. **Coi mọi lịch được phép ngắt việc.** Nếu đề cho phép preemption hoặc nhiều máy, không thể sử dụng trực tiếp chứng minh đổi chỗ của một máy chạy tuần tự không ngắt.
12. **Sai xử lý mảng rỗng hoặc tie.** Hãy định nghĩa rõ đầu ra cho n=0 và quy tắc hòa để có kết quả xác định.
13. **Đếm chi phí vét cạn vào greedy.** Duyệt hoán vị chỉ xuất hiện ở phần kiểm thử, không phải phần thuật toán chạy sản xuất.
14. **Quên setup/precedence.** Khi đổi hai công việc làm thay đổi thời lượng setup hoặc vi phạm phụ thuộc, lập luận tổng thời lượng không đổi không còn đủ.

## 15. Bảng kiểm thử biên cho một hiện thực EDD

| Tình huống | Dữ liệu ví dụ | Điều cần đúng |
| --- | --- | --- |
| Không có công việc | [] | L_max=0 theo quy ước API |
| Một công việc | p=3, d=5 | C=3, L_max=−2 |
| Hai việc hạn ngược thứ tự | (p=4,d=4), (p=1,d=100) | EDD làm việc hạn 4 trước, L_max=0 |
| Hạn bằng nhau | ID 8 và 3, cùng d=10 | Chương trình xếp ID 3 trước ID 8 |
| Công việc p=0 | (p=0,d=−2) | Completion không đổi nhưng L=2 |
| Deadline âm | (p=2,d=−1) | L=3, vẫn đúng phép tính |
| Thời lượng âm | (p=−1,d=5) | IllegalArgumentException |
| ID trùng | Hai job cùng ID | IllegalArgumentException |
| Phần tử null | Job[] chứa null | IllegalArgumentException |
| Toàn mảng null | input=null | IllegalArgumentException |
| Lượng thời gian rất lớn | Long có tổng vượt MAX_VALUE | ArithmeticException nhờ addExact |
| Toàn bộ lịch xong sớm | p=2, p=1, d đều 10 | L_max=−7, T_max=0 |

Lưu ý: khi mọi công việc trong bộ test có deadline lớn, so sánh chỉ T_max có thể trả 0 cho nhiều lịch không tối ưu theo L_max; kiểm thử riêng **L_max có dấu** giúp phân biệt tốt hơn.

Đối với các tình huống có ID trùng hoặc job null, mục tiêu kiểm thử không phải tìm ra một thứ tự tối ưu, mà là xác minh chương trình **từ chối đúng dữ liệu ngoài hợp đồng**.

## 16. Phân biệt với các mục tiêu lập lịch khác

| Mục tiêu | Ý nghĩa | Quy tắc thường gắn với mô hình đơn giản |
| --- | --- | --- |
| **Min L_max** | Giảm độ trễ có dấu lớn nhất | EDD, với một máy và mọi việc sẵn sàng từ 0 |
| **Min T_max** | Giảm phần quá hạn lớn nhất | EDD cũng tối ưu trong cùng mô hình vì T_max = max(0,L_max) |
| **Min tổng completion** | Giảm tổng thời điểm hoàn thành | SPT trong mô hình một máy, tất cả việc sẵn sàng từ 0 |
| **Min tổng tardiness** | Giảm tổng max(0,C_i−d_i) | Không được mặc định EDD; bài toán khó hơn |
| **Min số việc trễ** | Giảm số công việc có C_i > d_i | Không được mặc định EDD; cần phương pháp khác |
| **Min makespan C_max** | Giảm thời điểm toàn bộ lịch kết thúc | Với một máy, mọi việc bắt đầu từ 0 và không idle, mọi thứ tự đều có tổng p như nhau |

Ví dụ về makespan: bốn công việc có tổng p bằng 10 thì lịch không idle nào cũng kết thúc tại t=10, dù L_max có thể khác nhau rất nhiều. Điều này cho thấy một chiến lược “tối ưu” **chỉ có ý nghĩa so với hàm mục tiêu được xác định**.

Trong thực hành, EDD rất hữu ích để quản lý ưu tiên deadline, nhưng thiết kế sản xuất có thể còn yêu cầu công bằng, phân bổ tài nguyên, độ tin cậy, setup, ưu tiên khách hàng và chính sách ngắt việc. Các yếu tố đó đòi hỏi mô hình và chứng minh/đánh giá lại, không thể bảo đảm bằng tên thuật toán.

## 17. Bài tập thực hành và hướng phát triển

**Bài 1 — Chứng minh đổi chỗ:** cho hai công việc kề nhau i rồi j với d_i > d_j. Tự viết lại bốn độ trễ trước và sau khi đổi, chứng minh L'_i ≤ L_j và L'_j ≤ L_j, rồi giải thích tại sao các việc phía sau có cùng completion.

**Bài 2 — Phân biệt độ trễ với quá hạn:** với ba công việc có p lần lượt [2,3,1] và d lần lượt [10,20,30], hãy tính L_max, T_max dưới lịch EDD. Đổi hạn để một việc bị trễ và quan sát sự khác nhau giữa hai chỉ số.

**Bài 3 — Tạo oracle:** viết hàm đệ quy hoán vị một mảng tối đa sáu công việc, tính L_max từng hoán vị và đối chiếu EDD trên 100 ca ngẫu nhiên với seed cố định. Không dùng EDD làm oracle cho chính EDD.

**Bài 4 — Release time:** dựng lại lịch của ví dụ A(r=0,p=5,d=100), B(r=1,p=1,d=2), giải thích vì sao chờ một đơn vị thời gian có thể cho L_max thấp hơn việc chạy ngay A. Nêu bước nào trong chứng minh chuẩn không còn áp dụng.

**Bài 5 — Khôi phục thông tin:** mở rộng record Job để mang thêm tên và nhóm thực hiện; giữ đúng ID khi sắp xếp, trả lịch gồm thời điểm bắt đầu và hoàn tất của từng công việc. So sánh kết quả trước/sau khi thêm công việc deadline sớm.

**Checklist trước khi áp dụng EDD:** có đúng một máy không? Mọi việc sẵn sàng lúc 0 không? Có yêu cầu ngắt, setup hoặc precedence không? Hàm mục tiêu có đúng là L_max hay T_max không? Deadline và processing dùng cùng đơn vị thời gian không? Kết quả cần thứ tự ID hay chỉ giá trị L_max? Các phép cộng/trừ có nguy cơ overflow không?

**Kết luận:** quy tắc EDD dễ cài đặt, nhưng sức mạnh của nó nằm ở **chứng minh đổi chỗ**. Khi một cặp công việc đứng sai thứ tự deadline, đổi hai công việc kề nhau không làm độ trễ lớn nhất tăng; lặp lại sẽ tạo một lịch sắp theo deadline không giảm. Đó là khuôn suy nghĩ cốt lõi của tham lam: **một lựa chọn cục bộ được chứng minh không loại bỏ nghiệm tối ưu**, rồi ghép thành lời giải toàn cục.
