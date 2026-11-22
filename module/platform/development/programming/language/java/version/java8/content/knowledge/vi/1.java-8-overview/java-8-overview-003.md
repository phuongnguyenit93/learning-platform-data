# Đồng thời (concurrency) và song song (parallelism) trong Java 8

## Mục tiêu học tập

Sau bài này, bạn có thể phân biệt **đồng thời** với **song song**, nhận ra mối liên hệ giữa chúng với luồng, tác vụ, bất đồng bộ và tính an toàn dữ liệu; giải thích vì sao hai tác vụ có thể cùng tiến triển trên một nhân CPU nhưng không thực sự chạy cùng một thời điểm; và lựa chọn công cụ Java phù hợp theo đặc điểm công việc.

## 1. Hai khái niệm khác nhau ở điều gì?

**Đồng thời (concurrency)** là khả năng một hệ thống quản lý nhiều công việc có khoảng thời gian tồn tại hoặc tiến triển chồng lấn nhau. Hệ thống có thể tạm dừng việc A, chuyển sang B rồi quay lại A, miễn là mỗi việc có cơ hội tiến triển. Đồng thời tập trung vào **cách tổ chức và phối hợp công việc**.

**Song song (parallelism)** là việc hai hay nhiều công việc thực sự được thực thi **cùng một thời điểm**, thường trên các nhân CPU khác nhau hoặc tài nguyên xử lý độc lập. Song song tập trung vào **khả năng thực thi đồng thời về mặt vật lý**, thường nhằm giảm thời gian xử lý tác vụ có thể chia nhỏ.

Một hệ thống có thể có đồng thời mà không có song song. Chẳng hạn, một luồng xử lý lần lượt từng bước ngắn của hai yêu cầu: A1, B1, A2, B2. Cả hai yêu cầu đều đang tiến triển trong cùng một khoảng thời gian nhưng tại từng thời điểm chỉ một bước được thực thi. Ngược lại, khi hai nhân CPU chạy bước A và bước B tại cùng một thời điểm, hệ thống có song song và cũng có đồng thời.

Bảng đối chiếu:

| Góc nhìn | Đồng thời | Song song |
| --- | --- | --- |
| Câu hỏi chính | Làm sao nhiều công việc cùng tiến triển và phối hợp? | Làm sao nhiều phép xử lý cùng diễn ra để tăng năng lực tính toán? |
| Cần nhiều nhân CPU? | Không. Một nhân vẫn có thể chuyển qua lại giữa các công việc. | Thực thi CPU thật sự đồng thời cần tài nguyên xử lý độc lập. |
| Cần nhiều luồng Java? | Không nhất thiết; một vòng lặp sự kiện cũng có thể xen kẽ nhiều công việc. | Thường dùng nhiều luồng/worker cho công việc CPU độc lập trong Java. |
| Thách thức điển hình | Lập lịch, chờ, phối hợp, chia sẻ trạng thái, phản hồi. | Chia việc, cân bằng tải, chi phí phối hợp, tranh chấp tài nguyên. |
| Kết quả mặc định | Có thể tăng khả năng đáp ứng hoặc phục vụ nhiều yêu cầu. | Có thể giảm thời gian chạy của một khối lượng tính toán chia được. |
| Điều không được bảo đảm | Không bảo đảm chạy trên nhiều nhân. | Không bảo đảm nhanh hơn, nhất là khi công việc quá nhỏ hoặc phụ thuộc nhau. |

Hình dung dòng thời gian (mỗi ô là một khoảng thời gian; sơ đồ chỉ mô tả ý tưởng):

~~~text
Một worker:      | A1 | B1 | A2 | B2 |          (xen kẽ, không chạy cùng lúc)
Worker 1:        | A1 | A2 | A3 |                 (có thể chạy song song)
Worker 2:        | B1 | B2 | B3 |
                   thời gian  ──────────>
~~~

Ở hàng đầu tiên, mỗi công việc phải được chia thành những bước có thể chuyển giao. Nếu một bước giữ CPU quá lâu và không nhường quyền xử lý, một worker vẫn có thể làm công việc kia bị chờ. Ở hai hàng cuối, có hai worker đủ điều kiện chạy trên các nhân khác nhau; hệ điều hành và tài nguyên thực tế quyết định chúng có thực sự chạy song song hay không.

## 2. Phân biệt với đa luồng, bất đồng bộ và không chặn

Các từ này liên quan nhau nhưng không thay thế cho nhau:

- **Tác vụ (task):** đơn vị công việc cần hoàn thành, ví dụ xử lý một yêu cầu hoặc tính tổng một dãy số.
- **Luồng (thread):** đơn vị thực thi mà hệ điều hành/JVM có thể lập lịch. Nhiều luồng Java tạo điều kiện cho đồng thời và có thể tạo ra song song trên máy nhiều nhân; số luồng không bằng số nhân CPU.
- **Bất đồng bộ (asynchronous):** người gọi khởi động công việc và có thể tiếp tục việc khác trước khi lấy kết quả. Bất đồng bộ mô tả cách phối hợp **thời điểm nhận kết quả**, không tự khẳng định công việc chạy song song.
- **Không chặn (non-blocking):** lời gọi hoặc cơ chế có thể tiếp tục mà không phải đợi bằng cách chiếm giữ luồng ở điểm chờ. Không phải mọi API bất đồng bộ đều không chặn; ví dụ một tác vụ chạy bất đồng bộ vẫn có thể gọi I/O chặn bên trong worker.
- **Đa luồng (multithreading):** dùng nhiều luồng. Một chương trình đa luồng vẫn có thể chỉ được phân thời gian trên một nhân hoặc bị khóa làm các đoạn việc chạy tuần tự.

Ví dụ: CompletableFuture.supplyAsync(...) trong Java 8 có thể lên lịch một tác vụ để người gọi tiếp tục; việc tác vụ đó chạy song song với tác vụ khác còn phụ thuộc executor, số worker, CPU và mức tải. CompletableFuture không phải lời hứa về tốc độ. Future.get() và CompletableFuture.join() đều là các điểm có thể phải chờ kết quả.

Tương tự, hai yêu cầu HTTP được phục vụ xen kẽ là câu chuyện đồng thời; hai phép tính độc lập được chia cho hai nhân là cơ hội song song. Một dịch vụ thực tế thường cần **cả hai**: tổ chức nhiều yêu cầu đang hoạt động và dùng song song có kiểm soát ở những công đoạn phù hợp.

## 3. Java 8: đồng thời trên một worker bằng chia bước

Đoạn sau minh họa cách hai công việc logic cùng tiến triển khi chỉ có một worker. Mỗi bước được đưa vào hàng đợi như một tác vụ riêng; không có hai bước chạy cùng thời điểm. Đây là mô hình đơn giản để nhìn rõ sự xen kẽ, không phải bộ lập lịch có thể tự tạm dừng một phương thức đang chạy.

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class InterleavingDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();

        try {
            List<Future<?>> steps = Arrays.asList(
                worker.submit(() -> System.out.println("A: bước 1")),
                worker.submit(() -> System.out.println("B: bước 1")),
                worker.submit(() -> System.out.println("A: bước 2")),
                worker.submit(() -> System.out.println("B: bước 2"))
            );

            for (Future<?> step : steps) {
                step.get(); // Chờ từng bước hoàn thành và nhận lỗi nếu có.
            }
        } finally {
            worker.shutdown();
        }
    }
}
~~~

Lưu thành InterleavingDemo.java rồi chạy:

~~~bash
javac -encoding UTF-8 InterleavingDemo.java
java InterleavingDemo
~~~

Kết quả:

~~~text
A: bước 1
B: bước 1
A: bước 2
B: bước 2
~~~

Với newSingleThreadExecutor(), tác vụ đã được chấp nhận sẽ chạy tuần tự theo thứ tự xếp hàng. Hai công việc A/B xen kẽ **vì người lập trình chủ động chia chúng thành bước**. Nếu A được gửi thành một tác vụ dài duy nhất, B sẽ đợi A; việc chỉ tạo ExecutorService không tự biến đoạn mã đồng bộ dài thành quy trình có thể chuyển bước.

Bài học quan trọng: đồng thời là một đặc điểm của **tổ chức tiến độ công việc**, không phải cuộc đua tạo càng nhiều luồng càng tốt.

## 4. Java 8: tạo cơ hội song song cho công việc CPU độc lập

Khi công việc có thể chia thành các phần độc lập, hai worker cho phép thực hiện các phần đó trên những nhân khác nhau. Ví dụ tính tổng bình phương từ 1 đến 100.000, chia làm hai nửa:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ParallelWorkDemo {
    private static long sumSquares(long from, long to) {
        long sum = 0L;
        for (long i = from; i <= to; i++) {
            sum += i * i;
        }
        return sum;
    }

    public static void main(String[] args) throws Exception {
        long n = 100_000L;
        ExecutorService workers = Executors.newFixedThreadPool(2);

        try {
            Future<Long> left =
                workers.submit(() -> sumSquares(1L, n / 2));
            Future<Long> right =
                workers.submit(() -> sumSquares(n / 2 + 1, n));

            long combined = left.get() + right.get();
            long sequential = sumSquares(1L, n);

            System.out.println("Kết quả bằng nhau: " + (combined == sequential));
        } finally {
            workers.shutdown();
        }
    }
}
~~~

Lưu thành ParallelWorkDemo.java rồi chạy:

~~~bash
javac -encoding UTF-8 ParallelWorkDemo.java
java ParallelWorkDemo
~~~

Kết quả:

~~~text
Kết quả bằng nhau: true
~~~

Hai lệnh submit gửi hai phần việc độc lập đến executor có tối đa hai worker; Future.get() chờ mỗi phần trả về hoặc báo lỗi. Chỉ luồng gọi mới cộng hai kết quả, vì vậy không có biến tổng dùng chung để các worker cùng sửa. Ví dụ chứng minh **tính đúng của việc chia và ghép**, không chứng minh đã chạy nhanh hơn: phần việc rất nhỏ có thể tốn nhiều chi phí lập lịch hơn lợi ích thu được, và số nhân/mức tải ảnh hưởng đến tốc độ thực tế. Muốn so sánh hiệu năng, cần đo có làm nóng JVM, nhiều lần chạy, cùng dữ liệu, và nên dùng công cụ như JMH cho phép đo vi mô.

Một phép thử dùng Thread.sleep(...) chỉ đo khả năng các khoảng chờ chồng lấn, **không phải** bằng chứng rằng CPU xử lý phép tính nhanh gấp đôi.

## 5. Đúng kết quả trước, rồi mới tối ưu

Khi nhiều luồng cùng truy cập dữ liệu, đồng thời có thể dẫn tới **race condition**: kết quả phụ thuộc thứ tự các thao tác. Chẳng hạn biểu thức counter++ gồm đọc, cộng, ghi; hai luồng có thể cùng đọc một giá trị và làm mất lượt tăng. Khai báo volatile giúp vấn đề nhìn thấy cập nhật trong những tình huống phù hợp, nhưng **không biến counter++ thành thao tác nguyên tử**.

Ví dụ dùng AtomicInteger để đếm an toàn:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class SafeCounterDemo {
    public static void main(String[] args) throws Exception {
        AtomicInteger counter = new AtomicInteger(0);
        ExecutorService workers = Executors.newFixedThreadPool(2);

        Runnable increment = () -> {
            for (int i = 0; i < 100_000; i++) {
                counter.incrementAndGet();
            }
        };

        try {
            Future<?> first = workers.submit(increment);
            Future<?> second = workers.submit(increment);
            first.get();
            second.get();
            System.out.println("Tổng lượt tăng: " + counter.get());
        } finally {
            workers.shutdown();
        }
    }
}
~~~

Lưu thành SafeCounterDemo.java rồi chạy:

~~~bash
javac -encoding UTF-8 SafeCounterDemo.java
java SafeCounterDemo
~~~

Kết quả:

~~~text
Tổng lượt tăng: 200000
~~~

Cả hai worker cùng dùng counter, nhưng incrementAndGet() cập nhật nguyên tử. Future.get() vừa báo lỗi của tác vụ (nếu có) vừa tạo quan hệ đảm bảo nhìn thấy kết quả đã hoàn thành theo quy tắc bộ nhớ của java.util.concurrent. Ngược lại, thay incrementAndGet() bằng thao tác đọc rồi ghi thông thường có thể làm mất lượt tăng; không nên viết bài kiểm tra kỳ vọng một con số sai cụ thể vì lịch chạy thay đổi.

Khi thiết kế, ưu tiên **không chia sẻ trạng thái có thể thay đổi**: chia dữ liệu đầu vào, mỗi worker tạo kết quả riêng rồi ghép ở một điểm xác định. Nếu cần chia sẻ, dùng cấu trúc phù hợp như AtomicInteger, ConcurrentHashMap, synchronized hoặc Lock theo đúng thao tác cần bảo vệ. Các công cụ này bảo đảm tính đúng khi dùng đúng cách nhưng bản thân chúng không làm ứng dụng nhanh hơn.

Một số rủi ro còn lại: hai tác vụ giữ khóa theo thứ tự ngược nhau có thể gây deadlock; quá nhiều worker tranh CPU làm tăng chuyển ngữ cảnh; nhiều tác vụ chờ I/O trên pool nhỏ có thể gây nghẽn; và phụ thuộc dữ liệu giữa các phần có thể khiến song song khó đem lại lợi ích.

## 6. Chọn công cụ theo loại công việc

**Công việc thiên về CPU** (nén, tính toán, xử lý dữ liệu độc lập): xem có thể tách khối dữ liệu thành nhiều phần không; dùng một số worker phù hợp năng lực CPU, hạn chế chia sẻ dữ liệu và đo tốc độ sau khi xác minh kết quả. ExecutorService, ForkJoinPool và các phép toán song song trên stream là những công cụ khả dụng trong Java 8. Không nên mặc định rằng parallelStream() luôn tốt hơn stream(): với dữ liệu ít, thao tác nhẹ, nguồn khó tách hoặc phép xử lý có trạng thái chia sẻ, chi phí phối hợp có thể cao hơn lợi ích.

**Công việc thiên về I/O** (gọi mạng, đọc dữ liệu, chờ dịch vụ khác): trọng tâm thường là phục vụ thêm các yêu cầu trong lúc một số yêu cầu đang chờ. Java 8 có ExecutorService, CompletableFuture và các API I/O bất đồng bộ theo từng trường hợp. Dùng pool có giới hạn, timeout, cơ chế giới hạn lượng công việc chờ và xử lý lỗi rõ ràng; mở thật nhiều luồng không tự giải quyết nghẽn ở cơ sở dữ liệu hoặc dịch vụ bên ngoài.

**Chuỗi tác vụ phụ thuộc nhau**: nếu B cần kết quả của A, phần phụ thuộc đó phải chờ; thêm worker không khiến B có dữ liệu sớm hơn. Với CompletableFuture, các phép như thenApply nối bước xử lý kết quả; thenCombine kết hợp các kết quả độc lập. Cần phân biệt biến thể *Async với biến thể không có Async, và chú ý executor đang được sử dụng. Đừng gọi get()/join() quá sớm rồi vô tình chặn luồng gọi ở ngay điểm vừa tạo tác vụ.

**Lưu ý về môi trường Java hiện nay:** Java 8 là bối cảnh của ví dụ, còn các nguyên lý trên vẫn áp dụng cho JDK mới. Virtual threads trên Java 21+ là một lựa chọn hiện đại cho nhiều tác vụ chờ I/O, nhưng không tự tạo thêm nhân CPU và không biến tác vụ CPU thành nhanh hơn; chúng không phải API của Java 8. Khi làm việc trên phiên bản JVM mới, đánh giá công cụ phù hợp với phiên bản đang triển khai, thay vì mặc định mọi bài toán phải dùng thread pool truyền thống.

## 7. Những ngộ nhận cần tránh

1. **“Có hai thread nghĩa là có song song.”** Không chắc: máy có thể chỉ cho chúng xen kẽ, hoặc một luồng đang đợi khóa/I/O.
2. **“Đồng thời nghĩa là cùng một thời điểm.”** Trong lập trình, các khoảng tiến triển có thể chồng lấn mà các bước thực thi vẫn lần lượt.
3. **“Bất đồng bộ nghĩa là không chặn và chạy trên nhân khác.”** Đây là những tính chất độc lập; phải kiểm tra API và executor cụ thể.
4. **“Càng nhiều thread càng nhanh.”** Nhiều luồng làm tăng chi phí, tranh chấp và áp lực bộ nhớ; số worker phù hợp phụ thuộc CPU, I/O và giới hạn hệ thống.
5. **“Dùng parallelStream() sẽ an toàn với mọi thao tác.”** Side effect lên ArrayList, HashMap hoặc biến tích lũy dùng chung có thể không an toàn; ưu tiên phép biến đổi không trạng thái và collector phù hợp.
6. **“volatile giải quyết mọi race condition.”** volatile không làm chuỗi đọc–sửa–ghi thành nguyên tử.
7. **“Chạy nhanh một lần là đủ chứng minh.”** Kết quả phụ thuộc JIT, GC, cỡ dữ liệu, máy và tác vụ nền; phải xác nhận kết quả đúng trước khi đo.
8. **“Future.get() chỉ lấy giá trị.”** Lời gọi có thể chặn, ném ngoại lệ và là điểm đồng bộ hóa; vị trí gọi ảnh hưởng khả năng các tác vụ chồng lấn.

## 8. Tình huống thực hành và tự kiểm tra

**Tình huống A.** Một ứng dụng trên một nhân CPU nhận hai yêu cầu. Khi yêu cầu thứ nhất chờ mạng, ứng dụng xử lý yêu cầu thứ hai. Đây là biểu hiện của **đồng thời**; không đủ bằng chứng để khẳng định hai đoạn CPU chạy song song.

**Tình huống B.** Một phép tính chia được thành hai nửa hoàn toàn độc lập, chạy trên hai nhân CPU, kết quả ghép lại giống cách tính tuần tự. Đây là ứng dụng **song song**; mức tăng tốc thực tế còn phụ thuộc tỷ lệ công việc không thể chia và chi phí phối hợp.

**Tình huống C.** Một tác vụ thêm phần tử vào ArrayList trong lúc tác vụ khác đọc hoặc sửa chính danh sách ấy mà không phối hợp. Dù hệ thống có nhiều nhân hay một nhân, vẫn có nguy cơ sai kết quả do chia sẻ trạng thái.

**Tự thực hành:**
1. Trong InterleavingDemo, thay thứ tự gửi các bước thành A1, A2, B1, B2. Quan sát việc đổi lịch xen kẽ mà số worker không đổi. Sau đó thử gom A1 và A2 thành một tác vụ và giải thích vì sao worker không tự chuyển sang B giữa hai lệnh.
2. Trong ParallelWorkDemo, thay n bằng một giá trị lớn hơn nhưng vẫn không làm tổng bình phương vượt phạm vi long. So sánh cách chia 1, 2 và nhiều phần; bảo đảm kết quả bằng phiên bản tuần tự rồi mới đo.
3. Trong SafeCounterDemo, giải thích vì sao hai lần gọi get() trước khi đọc counter giúp kiểm tra tổng hoàn tất, và vì sao AtomicInteger cần thiết khi cùng cập nhật một biến.

**Câu hỏi ôn tập:** Một hệ thống một nhân CPU có thể đồng thời không? **Có**, bằng cách chia thời gian hoặc xen kẽ các bước. Hai Future đang chờ có chứng minh hai CPU xử lý song song không? **Không**. Tăng số luồng có làm một truy vấn cơ sở dữ liệu đơn lẻ nhanh hơn không? **Không mặc nhiên**; nút thắt có thể nằm tại truy vấn hoặc máy chủ cơ sở dữ liệu.

## Ghi nhớ

**Đồng thời = quản lý nhiều công việc đang tiến triển. Song song = thực thi nhiều phần việc thực sự cùng lúc.** Đồng thời giúp tổ chức và đáp ứng; song song có thể tăng năng lực tính toán. Trong Java, hãy xác định công việc phụ thuộc hay độc lập, thiên CPU hay I/O, có chia sẻ dữ liệu hay không, rồi chọn executor/công cụ phù hợp và kiểm tra tính đúng trước khi đo hiệu năng.