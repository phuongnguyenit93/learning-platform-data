# Java 10 – Handshake theo luồng: Khác biệt với yêu cầu dừng tất cả luồng

> **Bối cảnh:** Java 10 → **Handshake theo luồng** → **Khác biệt với yêu cầu dừng tất cả luồng**. **JEP 312 – Thread-Local Handshakes** thêm cơ chế nội bộ cho HotSpot để thực hiện một thao tác an toàn trên **một hoặc một tập JavaThread được chọn** mà không nhất thiết phải đưa **mọi Java thread** vào một **global VM safepoint**. Trọng tâm của bài là **phạm vi phối hợp, tính nhất quán, độ trễ và những giới hạn không thể thay thế Stop-the-World (STW)**. Kiến thức được trình bày theo các khái niệm vẫn áp dụng trên Java 17+ và các JDK hiện đại; không dựa vào cờ JVM đã bị loại bỏ hoặc API không được hỗ trợ.

## 1. Kết quả học tập và ý chính

Sau bài học, bạn có thể:

1. Nêu chính xác thay đổi do **JEP 312** bổ sung từ Java 10.
2. Phân biệt **thread-local handshake** với **global safepoint** và **Stop-the-World**.
3. Hiểu tại sao việc thao tác trên **một thread** không nhất thiết phải dừng **toàn bộ các Java threads khác**.
4. Mô tả các cách JVM thực thi callback: do **target JavaThread** tự xử lý hoặc bởi **VM thread** khi trạng thái target an toàn và nó đang bị chặn phù hợp.
5. Giải thích cơ chế **per-thread polling** và tại sao handshake không được phép tùy tiện quan sát hoặc sửa stack của một thread đang chạy bất kỳ lệnh nào.
6. Biết **all-thread handshake** vẫn khác global safepoint ở khả năng **từng thread hoàn thành rồi tiếp tục** mà không đợi tất cả thread hoàn thành cùng một thao tác.
7. Nhận biết rằng thread-local handshake **không tạo snapshot toàn JVM tại một thời điểm duy nhất**.
8. Hiểu vì sao **một số việc của GC, deoptimization, JVMTI/serviceability** có thể tận dụng cơ chế này nhưng **không phải mọi GC pause được thay thế**.
9. Phân biệt một **Java-level cooperative checkpoint** với **HotSpot thread-local handshake nội bộ**; ví dụ Java thuần chỉ mô phỏng phạm vi, không trực tiếp gọi JEP 312.
10. Dùng **unified logging** và **JFR** để điều tra global safepoints cùng các sự kiện JVM liên quan mà không dựa trên log format cố định.
11. Hiểu giới hạn: native code/JNI, thread state, polling frequency, OS scheduling, contention và virtual threads.
12. Tránh sử dụng `Thread.stop`, `Thread.suspend`/`resume` hoặc các giả định về public handshake API.
13. Phân biệt **global safepoint time**, **time-to-safepoint**, **operation duration**, **thread handshake latency** và **request latency**.
14. Thiết kế test/benchmark công bằng để đánh giá ảnh hưởng thay vì suy diễn từ số thread hay số dòng log.
15. Biên dịch/chạy chương trình Java 17+ minh họa **checkpoint một thread** đối chiếu **checkpoint cả hai worker**, rồi nhìn thấy global safepoint trong log HotSpot.

**Kết luận nhanh:** **Handshake cục bộ:** JVM chỉ cần phối hợp những JavaThread liên quan; JavaThreads không phải mục tiêu có thể tiếp tục. **Global safepoint:** JVM yêu cầu tập JavaThreads thích hợp đạt trạng thái an toàn toàn cục trước khi thực hiện một operation cần sự nhất quán toàn JVM. JEP 312 làm cơ chế xử lý **cục bộ** linh hoạt hơn, chứ không làm cho tất cả các công việc vốn cần STW trở thành concurrent.

## 2. Thuật ngữ: JavaThread, safepoint và handshake

### 2.1. `JavaThread` trong HotSpot không phải chỉ là object `Thread`

Trong mã nguồn HotSpot, **JavaThread** là kiểu nội bộ của JVM đại diện cho một thread thực thi Java trong một số ngữ cảnh. JEP 312 nhắm vào **cơ chế JVM xử lý JavaThread**, không phải một API công khai tên `Thread.handshake(...)`.

Trong Java application, bạn dùng `java.lang.Thread`, `Runnable`, `ExecutorService` hoặc virtual threads; **không có Java SE public API** cho phép truyền một callback tùy ý vào cơ chế `Handshake::execute` nội bộ HotSpot. JEP 312 là **nền tảng thực thi của VM**.

### 2.2. Safepoint là trạng thái an toàn, không phải trạng thái `WAITING` của Java

Một **safepoint** trong HotSpot là điều kiện JVM có thể thực hiện các thao tác nội bộ cần biết vị trí references/GC roots và trạng thái của Java threads một cách an toàn. JVM/JIT/interpreter cung cấp những vị trí hoặc trạng thái cho phép phối hợp này.

**Không đồng nhất:**

- `Thread.State.WAITING` hoặc `TIMED_WAITING`: trạng thái do Java API mô tả khi thread đang đợi.
- **Safepoint-safe:** trạng thái nội bộ mà VM có thể quan sát/xử lý các invariants cần thiết.
- **Global safepoint:** điều kiện phối hợp toàn JVM dành cho một VM operation.
- **Thread-local handshake:** yêu cầu an toàn có phạm vi những JavaThreads được chọn.

Một thread đang `RUNNABLE` ở Java-level vẫn có thể đi qua một điểm polling/safepoint rất ngắn. Một thread đang blocked/native có thể được coi là an toàn cho một số công việc VM mà không nhất thiết phải “đánh thức để đi vào Java code”.

### 2.3. Stop-the-World có nghĩa gì?

**STW** có nghĩa các application mutator threads không tiếp tục thực thi Java heap-mutating code trong thời gian JVM thực hiện operation yêu cầu global safepoint. Nói “dừng tất cả luồng” là cách diễn đạt dễ học nhưng **không hoàn toàn đồng nghĩa mọi native OS thread trong tiến trình bị đóng băng**: VM/GC/compiler/non-Java threads có thể vẫn hoạt động; Java threads ở native/JNI state có các quy tắc an toàn và kiểm tra khi quay lại Java.

Vì vậy khi so sánh hai cơ chế, hãy nói chính xác **“global VM safepoint đối với tập Java threads của VM”**, không tưởng tượng hệ điều hành suspend mọi thread ở mọi trạng thái.

## 3. Trước Java 10: Vì sao yêu cầu dừng toàn cục gây chi phí?

Trong cơ chế truyền thống, một số thao tác VM muốn xử lý thông tin của một JavaThread phải tận dụng **global safepoint**:

~~~text
VM muốn kiểm tra/thay đổi trạng thái của thread B
        |
        v
Yêu cầu global safepoint
        |
        +--> Thread A phải tới trạng thái an toàn
        +--> Thread B phải tới trạng thái an toàn
        +--> Thread C phải tới trạng thái an toàn
        +--> ...
        |
        v
Thao tác cần thiết
        |
        v
Toàn bộ Java mutators được phép chạy lại
~~~

Nếu JVM có hàng trăm/hàng nghìn Java threads nhưng operation chỉ cần xử lý **B**, việc buộc **A, C và các threads khác** tham gia synchronization toàn cục có thể tạo overhead và ảnh hưởng latency không cần thiết.

Tuy nhiên có những operation **thật sự** cần một toàn cục nhất quán: ví dụ một số pha garbage collection cần nhìn trạng thái của mọi GC roots/heap trong điều kiện an toàn. JEP 312 không bỏ điều kiện đó.

**JEP 312** thay đổi nền tảng phối hợp, cho phép yêu cầu **thread-local callbacks** trong một số tình huống mà trước đây thường phải dùng global VM safepoint. Điều này mở đường cho một số subsystem/serviceability/collector tối ưu các hoạt động cục bộ.

## 4. Mô hình cơ bản của JEP 312 – Thread-Local Handshakes

Một **handshake operation** là callback được JVM sắp xếp thực hiện cho một hoặc nhiều JavaThread khi những thread đó đang ở **safepoint-safe state**. Trong mô tả JEP:

- Callback có thể do **JavaThread mục tiêu tự thực thi** tại một điểm polling thích hợp.
- Hoặc do **VM thread** thực hiện thay khi target đang ở trạng thái đủ an toàn và được giữ blocked thích hợp.
- Handshake có thể nhắm **một JavaThread** hoặc nhiều JavaThreads.
- Không nhất thiết cần **global VM safepoint**.
- Một thread **có thể tiếp tục** sau khi xử lý xong operation của riêng nó.

~~~text
Request: chỉ handshake thread B

Thread A: ─────────────────────────────────────────► tiếp tục
Thread B: ────────[safe poll / callback]───────────► tiếp tục
Thread C: ─────────────────────────────────────────► tiếp tục

                         Không bắt buộc global safepoint
~~~

Đây là **mô tả logic**, không phải biểu đồ một lịch chạy cụ thể. Thread A/C vẫn có thể bị scheduler tạm ngưng, bị GC STW khác chặn hoặc tự đợi lock; ý nghĩa là **yêu cầu handshake đối với B không tự đặt ra hàng rào dừng toàn bộ A/C**.

### 4.1. Không phải interrupt, signal hay sleep

Một internal handshake không đơn giản là JVM gọi:

~~~java
target.interrupt();
~~~

`Thread.interrupt()` là cơ chế điều khiển/hợp tác ở mức Java, đặc biệt với các thao tác đợi được hỗ trợ; nó **không** cho phép JVM tùy ý an toàn đi qua Java frames/GC roots.

Tương tự, `Thread.sleep`, `CountDownLatch.await`, `LockSupport.park`, `ThreadLocal` hoặc synchronized block không phải API JEP 312. Chúng có thể giúp viết **mô hình trực giác**, nhưng không thay thế protocol và các invariants JVM.

### 4.2. Callback không luôn “chạy trên target thread”

JEP mô tả hai con đường thực thi callback. Khi target tự thực hiện, đó là **self-processing**. Khi VM thread xử lý thay, target phải trong trạng thái mà thao tác an toàn theo luật VM; callback không được chạy tùy ý trên một stack đang bị chỉnh sửa.

Đừng dạy quy tắc sai **“handshake callback chắc chắn luôn chạy trên JavaThread mục tiêu”** hoặc **“VM thread chỉ gửi tín hiệu, không bao giờ thực thi callback”**.

## 5. Global safepoint: một yêu cầu phối hợp khác về phạm vi

Với một **global safepoint**, VM yêu cầu tập JavaThreads thuộc protocol đạt trạng thái an toàn trước khi thực thi một operation cần điều kiện toàn cục. Mô hình logic:

~~~text
Request: global safepoint

Thread A: ─────────[safe / blocked]········┬──────► chạy lại
Thread B: ──────[safe / blocked]···········│──────► chạy lại
Thread C: ────────────[safe / blocked]·····│──────► chạy lại
                                           │
                                     VM operation
                                   ở global safepoint
                                           │
                                         hoàn tất
~~~

Điểm quan trọng:

1. VM không chỉ quan tâm một thread; nó phải chờ những threads cần phối hợp toàn cục.
2. **Time to reach safepoint** có thể chịu ảnh hưởng của một thread tới trạng thái an toàn chậm.
3. Trong thời gian operation tại safepoint, mutators không chạy code Java làm thay đổi heap theo cách không được phép.
4. Sau khi operation kết thúc, JVM cho threads tiếp tục.
5. Global safepoint không có nghĩa mọi thread cùng thực sự chạy một callback như ở **all-thread handshake**.

### 5.1. Những công việc vẫn cần STW

Tùy JDK và collector, các ví dụ còn hiện hữu gồm:

- Một số pha **Young/Mixed/Full GC** của các collectors dừng ứng dụng.
- Một số operation nội bộ cần invariants trên toàn bộ Java heap hoặc tập GC roots.
- Một số hoạt động deoptimization, class metadata/serviceability hoặc VM operation cần toàn JVM nhất quán.
- Các thao tác có event `SafepointBegin`/`SafepointEnd` trong JFR khi HotSpot thực sự thực hiện global safepoint.

Không khẳng định **mọi collector** hoặc **mọi GC phase** đều STW. Các collector hiện đại có nhiều công việc concurrent, và mỗi VM version có thể thay những operation trước đây toàn cục bằng cơ chế cục bộ. Phân biệt theo **event/log thực tế** và tài liệu JDK target.

## 6. Bảng đối chiếu trực tiếp: handshake vs dừng tất cả luồng

| Khía cạnh | Thread-local handshake | Global VM safepoint / STW |
| --- | --- | --- |
| **Phạm vi mục tiêu** | Một/một tập JavaThread cụ thể | Tập JavaThreads cần phối hợp toàn JVM |
| **Cần mọi JavaThread cùng đạt barrier?** | **Không nhất thiết** | **Có**, theo protocol global safepoint |
| **Threads không phải mục tiêu** | Có thể tiếp tục chạy Java | Không tiếp tục Java mutator work trong global stop |
| **Callback xử lý bởi ai?** | Target JavaThread hoặc VM thread khi an toàn | VM operation thực hiện khi điều kiện global đạt; chi tiết phụ thuộc operation |
| **Khi một thread xử lý xong** | Nó có thể tiếp tục độc lập | Threads đợi VM hoàn thành operation và giải phóng global safepoint |
| **Global snapshot đồng thời?** | **Không tự bảo đảm** | Có trạng thái global an toàn thích hợp với operation |
| **Chi phí phạm vi** | Thường giảm synchronization không cần thiết | Có overhead phối hợp trên toàn bộ Java threads |
| **Độ trễ chờ** | Phụ thuộc target(s), polling và trạng thái | Phụ thuộc việc toàn bộ threads cần thiết đạt safepoint |
| **Trường hợp áp dụng** | Công việc cục bộ đủ invariants, thread/serviceability/GC optimizations | Công việc yêu cầu ngừng Java heap mutation toàn JVM |
| **Có public Java API trực tiếp?** | **Không** | **Không** có API công khai “ép global safepoint” tổng quát |
| **Có bảo đảm không pause?** | **Không** đối với target; có thể xảy ra concurrent STW khác | Pause toàn VM theo điều kiện |
| **Có loại bỏ GC STW?** | Không | Chính một số GC phases sử dụng global safepoint |
| **Khả năng dùng trên virtual threads** | Không tự ánh xạ 1:1 với từng virtual thread | Phụ thuộc mô hình JVM/carrier và subsystem |
| **Cách quan sát** | JVM source/diagnostic log phù hợp; không mọi handshake được log | `-Xlog:safepoint`, JFR safepoint events |
| **Tính portable** | Chi tiết HotSpot internal, thay đổi theo JVM/JDK | Khái niệm safepoint STW phổ biến nhưng chi tiết VM-specific |

### 6.1. Một câu phân biệt dễ nhớ

**Global safepoint** như “cần tất cả nhân viên liên quan cùng tạm dừng để cập nhật toàn bộ sổ cái”. **Handshake một thread** như “chỉ cần kiểm tra trạng thái của một nhân viên khi người đó ở vị trí an toàn; đồng nghiệp vẫn có thể làm việc”.

Ẩn dụ không thay cho specification. Trong thực tế, VM operations có hệ thống khóa/barrier/threads và yêu cầu invariants chặt hơn các động tác con người; không vì có một cơ chế cục bộ mà có thể áp nó cho mọi operation.

## 7. Một thread handshake và “handshake tất cả threads” cũng khác nhau

JEP 312 cho phép callback thực thi trên **một hoặc nhiều JavaThreads**. Nếu JVM yêu cầu callback cho một tập lớn, thậm chí toàn bộ JavaThreads, vẫn không tự động biến nó thành **global safepoint**.

~~~text
All-thread handshake (trực giác):

A: ──[callback A]───► tiếp tục xử lý
B: ─────────[callback B]──► tiếp tục xử lý
C: ─────[callback C]──────► tiếp tục xử lý

Mọi target nhận operation; không bắt buộc chờ kết thúc cùng một lúc.
~~~

Điểm khác:

- Mỗi thread thực hiện callback khi ở **trạng thái an toàn của nó**.
- Hoàn thành của một thread có thể cho phép **thread ấy chạy tiếp**, không phải tất cả cùng chờ một global resume barrier.
- **Thời điểm xử lý trên A có thể khác thời điểm xử lý trên C**.
- Một operation cần snapshot **toàn heap nhất quán tại cùng thời điểm** không thể cứ thay global safepoint bằng việc hỏi A hôm nay và hỏi C sau đó.
- Nếu cơ chế VM cụ thể cần chờ tất cả callbacks hoàn thành để trả kết quả tổng hợp, thread **gọi yêu cầu** có thể phải đợi; điều này **không đồng nghĩa các target đã xử lý xong bị bắt đứng yên toàn thời gian**.

### 7.1. Tính nhất quán: một ví dụ dữ liệu

Giả sử A và B cùng tăng counters liên quan đến nhau:

~~~text
t1: handshake A, đọc counterA=7
t2: A và B tiếp tục thay đổi dữ liệu
t3: handshake B, đọc counterB=10
~~~

Không thể suy ra cặp `(7,10)` là một snapshot atomic của toàn hệ thống tại một thời điểm. Với nhu cầu một snapshot nhất quán, ứng dụng cần cơ chế synchronization hoặc protocol snapshot đúng theo nghiệp vụ; phía JVM cần global invariants tương ứng.

**Nhận biết sai lầm:** “Handshakes đã gọi trên tất cả threads, vậy dữ liệu nhận được có nghĩa tất cả threads đã dừng cùng một lúc”. Điều đó **không** được JEP 312 bảo đảm.

## 8. Cơ chế polling và trạng thái safepoint-safe

HotSpot có cơ chế kiểm tra khi thread đang thực thi Java interpreted/JIT code ở những vị trí an toàn. JEP 312 gắn với **per-thread polling** để VM có thể yêu cầu một mục tiêu thay vì chỉ bật một yêu cầu global chung.

Một đường đi đơn giản hóa:

~~~text
VM/service cần handshake của JavaThread B
           |
           v
Đưa operation vào trạng thái/queue tương ứng với B
           |
           v
Kích hoạt polling/điều kiện xử lý tại B
           |
           +----> Nếu B chạy Java, B tới safe poll và tự xử lý
           |
           +----> Nếu VM xác minh B ở safe state thích hợp,
                   VM thread có thể xử lý thay
           |
           v
Callback được thực thi an toàn
           |
           v
Dọn trạng thái handshake; B được tiếp tục khi điều kiện cho phép
~~~

Đây là **mô hình kiến trúc** cho mục đích học, không phải lời hứa về cấu trúc queue cụ thể của mọi version HotSpot. Mã nguồn `handshake.cpp`/`handshake.hpp` có thể đổi chi tiết, locks, helper thread và cách poll giữa các release.

### 8.1. Không đọc/ghi stack đang biến đổi tùy tiện

Khi JavaThread đang chạy, stack/registers/GC roots của nó có thể thay đổi theo lệnh vừa thực thi. Nếu VM muốn kiểm tra thông tin nhạy cảm, nó phải đợi **trạng thái có invariants phù hợp** hoặc phối hợp thread đó. Callback chỉ được thực hiện khi điều kiện này đúng; đó là ý nghĩa của “handshake in safepoint-safe state”.

### 8.2. Không phải mọi request được xử lý ngay lập tức

Dù chỉ nhắm một thread, handshake có thể bị chậm vì:

- Target chưa tới polling/safe transition thích hợp.
- Target ở native/JNI/VM state cần protocol đặc biệt.
- Thread đang trong điều kiện synchronization khó tiến triển.
- Target có công việc dài ở một code path với tần suất kiểm tra hạn chế.
- OS scheduler không cấp CPU ngay.
- VM đang thực hiện hoặc đợi một operation khác cần phối hợp.
- Locks/monitor contention hoặc điều kiện nội bộ của subsystem.

Vì vậy **handshake nhỏ phạm vi** không phải **real-time deadline**. Nó làm giảm một **nguồn** overhead toàn cục, nhưng không bảo đảm latency bằng 0 hoặc thời gian chờ không giới hạn bằng một con số cố định.

### 8.3. Native threads và JNI

Một JavaThread thực thi native code không giống thread đang sửa Java heap qua bytecode. HotSpot có thể đánh giá liệu trạng thái đó safepoint-safe, cần xử lý callback thay, hay cần đợi transition. Khi quay lại Java, các safepoint/handshake checks liên quan vẫn áp dụng.

**Không khẳng định** toàn bộ native OS threads bị ngừng tại global safepoint; cũng không khẳng định mọi thread JNI có thể bị thao tác callback ngay mà không cần kiểm tra trạng thái. Các chi tiết cụ thể phụ thuộc protocol và JDK.

## 9. Những cải tiến mà JEP 312 cho phép, và giới hạn cần hiểu

JEP 312 là một **building block** trong HotSpot:

- Cho phép những subsystem chỉ cần làm việc với **một JavaThread** tránh yêu cầu global safepoint trong các trường hợp an toàn.
- Tạo nền tảng cho các tối ưu **thread-local processing**, thread stack work/serviceability và công việc của GC ở các JDK sau.
- Có thể giảm **tần suất hoặc phạm vi** các lần dừng toàn cục do những operation trước đây cần VM-wide coordination.
- Có thể cải thiện scalability khi có rất nhiều JavaThreads.
- Không bắt buộc thay đổi Java source của ứng dụng; API Java concurrency bình thường vẫn chạy.

**Nhưng không được suy:**

1. JEP 312 loại bỏ global safepoints.
2. Nó biến một collector STW thành concurrent hoàn toàn.
3. Mọi thread dump/stack trace trong mọi JDK chỉ dùng handshake.
4. Mọi JVMTI operation có thể chạy mà không ngăn các threads khác.
5. Các callback handshake là user-defined Java lambdas.
6. Chi phí handshake luôn thấp hơn global safepoint trong mọi workload.
7. Có handshake nghĩa ứng dụng không thể thấy latency spikes.
8. Các optimization cũ/removed như **biased locking** là lời khuyên hiện đại để tận dụng JEP 312.

### 9.1. Không dùng biased locking như ví dụ cấu hình ngày nay

Tài liệu lịch sử về JEP 312 đôi khi nhắc khả năng hủy biased locks cục bộ thay vì dừng tất cả threads. Nhưng **biased locking đã bị vô hiệu hóa rồi bị loại bỏ trên các JDK mới hơn**. Bài học chỉ dùng ví dụ này như **bối cảnh lịch sử của động lực thiết kế**, không hướng dẫn bật `-XX:+UseBiasedLocking` hay các cờ liên quan trên JDK hiện đại.

Cách học bền vững: tập trung vào **safepoint/handshake protocol**, chứ không dựa trên một tối ưu locking từng tồn tại rồi không còn.

## 10. GC và handshakes: vì sao vẫn có Stop-the-World?

Một bộ thu gom rác cần xem xét những object còn reachable và có thể cần cập nhật/di chuyển objects, GC roots hoặc class metadata. Cách thực hiện phụ thuộc thuật toán collector và pha cụ thể.

- Với **G1**, những Young/Mixed pauses và đường Full GC vẫn có những đoạn **STW**.
- Một số collectors hiện đại có nhiều công việc concurrent và dùng các kỹ thuật phối hợp thread tinh vi, trong đó thread-local processing có thể hữu ích.
- Một số hoạt động trên **thread stacks/roots** có thể tối ưu bằng cơ chế per-thread handshakes khi invariants và collector cho phép.
- Vẫn có các operation yêu cầu **global safepoint** hoặc một dạng toàn cục synchronization phù hợp.

### 10.1. Không nên nói “có handshakes thì GC không pause”

Hai yêu cầu khác nhau:

~~~text
A. Operation: cập nhật/kiểm tra thông tin liên quan riêng thread B.
   Có thể sử dụng thread-local handshake nếu invariants cho phép.

B. Operation: xử lý heap/roots theo một global invariant cần
   mutators dừng đồng thời.
   Cần toàn cục synchronization/safepoint theo thuật toán.
~~~

JEP 312 làm trường hợp A dễ thực hiện hơn **không qua global safepoint**. Nó không tự biến B thành A.

### 10.2. Safepoint cho một VM operation chưa chắc là Full GC

Log `Safepoint "G1CollectFull"` nói rõ một VM operation liên quan GC; nhưng JVM còn có safepoints cho những lý do khác. Đừng gộp **số lần safepoint** với **số lần Full GC**. Khi điều tra latency, phân loại cause và thời gian của từng loại event.

### 10.3. G1 Full GC song song vẫn có STW

**Parallel** Full GC (JEP 307, cũng của Java 10) nghĩa nhiều GC workers cùng làm việc **khi application đã tạm dừng**. Nó là khái niệm **khác** với JEP 312 thread-local handshakes. Một cơ chế song song hóa việc GC không đồng nghĩa có thể cho các Java mutators khác tiếp tục mà không ảnh hưởng invariants.

## 11. Hệ quả về latency: phạm vi chờ quan trọng hơn số threads

### 11.1. Global safepoint có hai phần độ trễ đáng phân tích

Một mô hình khái niệm:

~~~text
Global elapsed time
≈ thời gian các JavaThreads cần thiết đạt safepoint
+ thời gian VM operation tại safepoint
+ chi phí phát hành/khôi phục threads
~~~

Trong log/JFR, các thành phần có thể được gắn tên khác nhau theo phiên bản. **Time to safepoint** lớn có thể do một thread chậm đến trạng thái an toàn; **time at safepoint** lớn có thể do chính operation như GC đang tốn thời gian.

Không gộp hết thành “thời gian GC dừng”, đặc biệt khi không phải event nào cũng là GC.

### 11.2. Thread-local handshake có phạm vi chờ khác

Một yêu cầu chỉ nhắm B có thể cần chờ **B** trở nên safepoint-safe, xử lý callback rồi tiếp tục. Threads A/C không tự bị chặn chỉ vì B chưa hoàn thành. Nếu yêu cầu nhắm 100 threads, việc hoàn tất toàn operation có thể cần chờ 100 callbacks, nhưng từng target có thể được giải phóng độc lập.

**Ý nghĩa performance:** Nếu một thread C bị chậm reaching safepoint, global safepoint có thể bị chậm bởi C; handshake chỉ cho B thường **không phải đợi C**. Tuy vậy locks/VM operations/scheduler có thể gây phụ thuộc gián tiếp; đừng quảng cáo “handshake B không bao giờ chịu ảnh hưởng C”.

### 11.3. Không có công thức speedup universal

Không thể viết “1000 threads thì handshakes nhanh gấp 1000” hay “mỗi handshake tốn đúng một poll”. Workload, thread state, machine topology, VM implementation, số targets và operations cùng lúc đều ảnh hưởng.

Hãy đo **latency distribution** của request thật, **global safepoint pauses**, GC latency và số lượng VM operations. Dùng JFR/GC logs/async profiler phù hợp với môi trường, không suy hiệu quả chỉ từ tên JEP.

## 12. Ví dụ Java 17+ độc lập: mô phỏng phạm vi phối hợp

**Lưu ý rất quan trọng về tính đúng đắn:** Không có public Java API để yêu cầu HotSpot thực hiện `Handshake::execute` cho một arbitrary JavaThread. Chương trình dưới đây dùng **hai application workers**, queue và `CountDownLatch` để **mô phỏng khác biệt về phạm vi phối hợp**. Nó **không phải** mã gọi JEP 312 bên trong JVM. Sau phần mô phỏng, chương trình gọi `System.gc()` trong một môi trường thử đã kiểm soát để tạo một event global safepoint có thể quan sát trong log.

### 12.1. Mô hình logic

~~~text
Lượt 1 – Chỉ giữ target:
  target: [job checkpoint -> đợi release]  ... rồi tiếp tục
  other:  [làm xong một job]               ... vẫn hoạt động

Lượt 2 – Giữ cả hai workers:
  target: [checkpoint] ... bị giữ tới releaseBoth
  other:  [checkpoint] ... bị giữ tới releaseBoth
  jobs tiếp sau: chưa được chạy khi cả hai workers vẫn bị giữ
  releaseBoth -> cả hai tiếp tục và chạy jobs sau barrier
~~~

Đây là **application-level cooperative controls** để minh họa, khác hoàn toàn một VM global safepoint: ngoài hai demo workers, main thread và các JVM threads khác vẫn chạy. Khi global safepoint thật diễn ra, protocol của HotSpot áp dụng cho các JavaThreads mà JVM cần dừng.

### 12.2. Chương trình Java đầy đủ

Lưu đúng tên **`HandshakeScopeDemo.java`**:

~~~java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class HandshakeScopeDemo {
    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Checkpoint timeout");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        }
    }

    private static final class Worker extends Thread {
        private static final Runnable STOP = () -> { };
        private final BlockingQueue<Runnable> commands = new LinkedBlockingQueue<>();

        Worker(String name) {
            super(name);
        }

        void submit(Runnable task) {
            commands.add(task);
        }

        void shutdown() {
            commands.add(STOP);
        }

        @Override
        public void run() {
            try {
                while (true) {
                    Runnable task = commands.take();
                    if (task == STOP) {
                        return;
                    }
                    task.run();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Worker target = new Worker("target");
        Worker other = new Worker("other");
        CountDownLatch releaseTarget = new CountDownLatch(1);
        CountDownLatch releaseBoth = new CountDownLatch(1);
        target.start();
        other.start();
        try {
            CountDownLatch targetReady = new CountDownLatch(1);
            CountDownLatch otherDone = new CountDownLatch(1);
            CountDownLatch targetContinued = new CountDownLatch(1);
            target.submit(() -> {
                targetReady.countDown();
                await(releaseTarget);
            });
            await(targetReady);
            other.submit(otherDone::countDown);
            await(otherDone);
            System.out.println("single-target-held=" +
                    (releaseTarget.getCount() == 1));
            System.out.println("other-progressed=true");
            releaseTarget.countDown();
            target.submit(targetContinued::countDown);
            await(targetContinued);
            System.out.println("target-resumed=true");

            CountDownLatch bothReady = new CountDownLatch(2);
            CountDownLatch bothDone = new CountDownLatch(2);
            AtomicInteger completed = new AtomicInteger();
            Runnable hold = () -> {
                bothReady.countDown();
                await(releaseBoth);
            };
            target.submit(hold);
            other.submit(hold);
            await(bothReady);
            Runnable afterward = () -> {
                completed.incrementAndGet();
                bothDone.countDown();
            };
            target.submit(afterward);
            other.submit(afterward);
            System.out.println("both-workers-held=" +
                    (releaseBoth.getCount() == 1));
            System.out.println("tasks-before-release=" + completed.get());
            releaseBoth.countDown();
            await(bothDone);
            System.out.println("tasks-after-release=" + completed.get());
        } finally {
            releaseTarget.countDown();
            releaseBoth.countDown();
            target.shutdown();
            other.shutdown();
            target.join(5000);
            other.join(5000);
        }
        System.out.println("workers-finished=" +
                (!target.isAlive() && !other.isAlive()));
        System.gc();
    }
}
~~~

### 12.3. Lệnh compile và chạy đã kiểm thử

~~~bash
javac --release 17 -encoding UTF-8 HandshakeScopeDemo.java

java -XX:+UseG1GC \
     -XX:-DisableExplicitGC \
     -XX:-ExplicitGCInvokesConcurrent \
     -Xlog:handshake=debug,safepoint=info:file=vm.log \
     HandshakeScopeDemo
~~~

Với Windows PowerShell, dùng một dòng vì POSIX `\` không phải dấu nối dòng PowerShell:

~~~powershell
javac --release 17 -encoding UTF-8 HandshakeScopeDemo.java
java -XX:+UseG1GC -XX:-DisableExplicitGC -XX:-ExplicitGCInvokesConcurrent "-Xlog:handshake=debug,safepoint=info:file=vm.log" HandshakeScopeDemo
~~~

Các cờ:

- `UseG1GC`: chọn G1 collector để event explicit GC dễ nhận diện.
- `DisableExplicitGC` ở trạng thái `-`: không bỏ qua `System.gc()` trong môi trường thử.
- `ExplicitGCInvokesConcurrent` ở trạng thái `-`: tránh chuyển explicit request sang đường concurrent trong cấu hình HotSpot thử.
- `-Xlog:...:file=vm.log`: đưa diagnostic logs vào **file**, không làm lẫn stdout.
- `handshake=debug` có thể không tạo log nếu workload không kích hoạt event được JVM log ở level ấy. **Không thấy log handshake không chứng minh JEP 312 bị tắt**.
- `safepoint=info`: log những event global safepoint được HotSpot ghi ở level đó.

**Không đặt `System.gc()` thường xuyên vào production để “giám sát handshake”**; đây là thao tác thử, có thể gây STW pause. Trên VM/collector/config khác, yêu cầu GC có thể được bỏ qua/chuyển kiểu và không tạo chính xác event như ví dụ.

### 12.4. Stdout chính xác đã kiểm chứng

~~~text
single-target-held=true
other-progressed=true
target-resumed=true
both-workers-held=true
tasks-before-release=0
tasks-after-release=2
workers-finished=true
~~~

Các dòng này độc lập với ID thread và thời điểm scheduler chạy, vì chương trình dùng latches để đồng bộ việc in. Trong một máy cực chậm/đang bị treo lâu, timeout 5 giây có thể làm demo ném exception thay vì in hết; đây là **giới hạn chủ đích của test**, không phải một cam kết độ trễ handshake của VM.

### 12.5. Giải thích từng dòng

1. `single-target-held=true`: sau khi target báo sẵn sàng, latch release của target chưa mở.
2. `other-progressed=true`: worker khác đã thực hiện xong job trong lúc target vẫn đang giữ checkpoint.
3. `target-resumed=true`: target tiếp tục xử lý job sau khi riêng latch của nó được mở.
4. `both-workers-held=true`: hai demo workers đã đạt barrier và chưa được giải phóng.
5. `tasks-before-release=0`: hai task xếp **sau barrier** chưa được worker nào chạy khi cả hai đang bị giữ.
6. `tasks-after-release=2`: cả hai workers xử lý xong tác vụ sau khi giải phóng barrier.
7. `workers-finished=true`: workers đã kết thúc có kiểm soát và join thành công.

**Cảnh báo diễn giải:** Những số `0` và `2` là **kết quả của hàng đợi/hợp tác của ứng dụng**, không phải thống kê global safepoint do HotSpot báo. Mô hình global ở đây là “chặn cả hai demo workers”, không chặn toàn bộ JVM.

### 12.6. Xác minh global safepoint thật trong log

Sau lệnh Java:

~~~bash
grep -i safepoint vm.log
~~~

hoặc PowerShell:

~~~powershell
Select-String -Path .\vm.log -Pattern "Safepoint"
~~~

Trong JDK/HotSpot đã kiểm thử, log có event tương đương:

~~~text
[info][safepoint] Safepoint "G1CollectFull",
  Time since last: ... ns,
  Reaching safepoint: ... ns,
  At safepoint: ... ns,
  Leaving safepoint: ... ns,
  Total: ... ns
~~~

Dòng trên **rút gọn các số/timestamp tùy môi trường**, không phải output byte-for-byte. Sự kiện này được kích hoạt bởi `System.gc()` trong cấu hình thử và là **global safepoint thật**, khác với latches mô phỏng phía trên.

Trong lần chạy HotSpot JDK hiện có, logfile có global safepoint `G1CollectFull` và không in dòng handshake debug; điều đó hoàn toàn phù hợp vì demo Java **không trực tiếp yêu cầu VM handshake**, và mức logging/operation nội bộ còn tùy version.

## 13. Tại sao `Thread.getStackTrace()` hoặc `ThreadMXBean` không phải public handshake API?

`Thread.getStackTrace()`, `Thread.getAllStackTraces()` và `ThreadMXBean.getThreadInfo(...)` là **Java management/diagnostic APIs** dùng để lấy thông tin thread.

~~~java
Thread target = Thread.currentThread();
StackTraceElement[] stack = target.getStackTrace();
System.out.println(stack.length > 0);
~~~

Ví dụ này chỉ cho thấy **public stack inspection**. Nó không nói callback HotSpot handshake được phát cho target, không bảo đảm runtime dùng hay không dùng global safepoint, và không cho Java program kiểm soát cách HotSpot thu thập stack.

**Không suy diễn:**

- “Vì chỉ yêu cầu stack của B nên chắc chắn JVM dùng local handshake cho B”.
- “Vì gọi `getAllStackTraces()` nên chắc chắn JVM dừng toàn bộ ứng dụng”.
- “Một snapshot stack do API trả về là atomic snapshot của mọi threads”.
- “Đọc thread info là thao tác không có pause/overhead”.

Điều JVM dùng để implement diagnostic API là **chi tiết có thể thay theo JDK, vendor, flags và trạng thái thread**. Nếu mục tiêu là tối ưu production profiling, đo trực tiếp với JFR/appropriate profiler và kiểm JDK release notes, không chỉ nhìn tên method.

### 13.1. Public API nào liên quan đến quản lý threads?

- `Thread.interrupt()`: yêu cầu một thread hợp tác thoát các thao tác interruptible hoặc kiểm trạng thái interrupt; không phải handshake VM.
- `Thread.join()`: thread gọi chờ target kết thúc; không phải global safepoint.
- `CountDownLatch`/`Phaser`/`CyclicBarrier`: đồng bộ có chủ đích của application threads; không tự thực hiện JVM safepoint.
- `LockSupport.park/unpark`: primitive quản lý parking; không cho quyền đọc stack bất kỳ thread đang chạy.
- `ThreadLocal`: lưu state theo thread; tên chứa “thread local” nhưng **không liên quan trực tiếp** đến JEP 312.
- `ThreadMXBean` và `JFR`: công cụ quan sát; không phải API phát arbitrary handshake callback.

### 13.2. Tránh những API dừng thread không an toàn

Các thao tác kiểu `Thread.stop`, `Thread.suspend` và `Thread.resume` đã bị deprecated/loại bỏ hoặc bị cảnh báo mạnh trong Java hiện đại vì nguy cơ làm hỏng invariants/giữ locks/corrupt state. **Không** dùng chúng để mô phỏng hoặc “tự cài đặt thread-local handshake” trong ứng dụng.

Thay vào đó, dùng **cooperative cancellation**, interruption, latches, executors và structured concurrency theo API/JDK hỗ trợ khi bài toán thực là phối hợp application threads.

## 14. Logging: phân biệt event safepoint và handshake

### 14.1. Hỏi JDK hiện tại có log tags nào

~~~bash
java -Xlog:help
~~~

Tìm những tags như `safepoint` và `handshake` khi HotSpot version hỗ trợ. Không ghi cứng một tổ hợp tags mà chưa kiểm runtime, vì JVM vendors và các releases có thể khác chi tiết diagnostic logging.

### 14.2. Chỉ quan sát global safepoints

~~~bash
java -Xlog:safepoint=info:file=safepoints.log -jar app.jar
~~~

Nếu cần chi tiết hơn trên HotSpot hỗ trợ:

~~~bash
java -Xlog:safepoint*=debug:file=safepoint-detail.log -jar app.jar
~~~

Giải thích:

- `safepoint=info` thường tập trung vào các events toàn cục.
- `safepoint*=debug` bật thêm tag combinations/verbosity; có thể tạo nhiều log/overhead.
- **Không có event global safepoint trong một khoảng** không đồng nghĩa “không có handshake”.
- **Có event safepoint** không có nghĩa JEP 312 bị tắt hay mọi VM operation bắt buộc STW.

### 14.3. Quan sát handshake (best-effort)

~~~bash
java -Xlog:handshake=debug:file=handshakes.log -jar app.jar
~~~

Log level/tag có thể không xuất bản tất cả internal handshakes ở mức đó; nội dung log phụ thuộc JDK và subsystem. Không cố kết luận handshake count bằng cách đếm vài dòng log khi docs JDK không cam kết mức bao phủ đó.

### 14.4. Không dùng log verbose mặc định ở mọi production instance

- Logging trace/debug có thể ảnh hưởng throughput và I/O.
- Phải giới hạn size/rotation/retention; dữ liệu thread names/stacks có thể chứa thông tin nhạy cảm.
- Nên bật thử trong môi trường đại diện hoặc trong khoảng giới hạn, dưới các cơ chế vận hành phù hợp.
- Đọc bản chính xác của JDK manual để xác định logging syntax và available tags.
- Khi so latency, bảo đảm biến logging không khác giữa baseline và phương án thử.

## 15. JFR và safepoint analysis

**Java Flight Recorder (JFR)** giúp thu thập các events runtime (tùy cấu hình recording, threshold và JDK version). Các sự kiện liên quan đến safepoints có thể xuất hiện với tên như:

- `jdk.SafepointBegin`.
- `jdk.SafepointEnd`.
- `jdk.SafepointStateSynchronization`.
- `jdk.ExecuteVMOperation` (có field về VM operation/safepoint trong bản hỗ trợ).
- Các GC-related events khác để biết pause/cause.

**Không phải JFR trên mọi JDK sẽ có cùng tập event đã bật mặc định hoặc cùng threshold**, và không phải mọi thread-local handshake đều có một event JFR riêng có thể quan sát được.

### 15.1. Một workflow quan sát hiện hành

1. Tạo JFR recording theo chính sách của ứng dụng/JDK.
2. Chạy workload đại diện.
3. Mở recording bằng JDK Mission Control hoặc dùng `jfr print` (khi CLI hỗ trợ).
4. Xem các global safepoint events, VM operation names và thời lượng.
5. Liên hệ với GC pause, thread counts, CPU saturation và request latency.
6. Nếu cần hiểu một subsystem cụ thể có dùng handshakes hay không, tham khảo docs/changelog/mã nguồn HotSpot **đúng release**, không đoán chỉ từ profile đồ họa.

Ví dụ CLI để xem một số event (thay file bằng recording thật):

~~~bash
jfr print --events jdk.SafepointBegin,jdk.SafepointEnd recording.jfr
~~~

Chỉ chạy khi file `recording.jfr` thực sự có; event nào không được thu thập sẽ không xuất hiện. Không cần dùng `Thread.stop` hoặc ép Full GC để ghi JFR trong workload production.

### 15.2. Phân loại thời gian

Nếu có global safepoint dài:

- **Reaching safepoint** lớn: xem vì sao JavaThreads đến điểm an toàn chậm.
- **At safepoint** lớn: xem VM operation/GC làm việc gì.
- **Leaving safepoint** lớn: xem thời gian giải phóng/khôi phục.
- **Request latency** lớn nhưng không có safepoint tương ứng: kiểm CPU scheduling, locks, DB/network, JIT, OS và các nguyên nhân khác.
- **Lượng handshake work** cao không tự đồng nghĩa có global pauses: cần phân biệt phạm vi cục bộ và chi phí tổng thể.

## 16. Thread states, native code và những cạnh biên cần hiểu

### 16.1. Thread không chạy Java lúc yêu cầu đến

Nếu một JavaThread đang:

- Blocked trong JVM primitive;
- Chờ I/O;
- Đang ở native code/JNI;
- Bị preempted bởi OS;
- Đang thực thi JIT code hoặc compiler-generated code;

HotSpot có các cơ chế/điều kiện khác nhau để xác định thread đã safepoint-safe hay cần đợi nó thực hiện một transition/poll phù hợp. **Không** tạo thuật toán đơn giản “luôn interrupt để ép đến handshake” vì nó không tương ứng protocol của VM.

### 16.2. Non-target threads có thể vẫn bị chặn bởi nguyên nhân khác

Một handshake đối với B không yêu cầu global safepoint, nhưng A có thể không tiến triển vì:

- A đang chờ lock do B nắm.
- A bị thiếu CPU scheduler time.
- Cùng lúc VM có GC STW.
- A tự chờ network, I/O, conditions.
- A bị backpressure hoặc thread pool starvation.

Do đó tính đúng đắn là **“cơ chế handshake cục bộ không tự buộc non-target threads dừng”**, không phải **“mọi non-target threads luôn chạy liên tục không một gián đoạn”**.

### 16.3. Đợi tại safe state không có nghĩa ứng dụng phải gọi `Thread.yield`

Interpreter/JIT/VM quản lý safepoint polling. Developer không phải chèn `Thread.yield()` hoặc `sleep(1)` vào các loops để “JEP 312 hoạt động”. Sửa ứng dụng bằng cách thêm sleep để chữa một issue handshake chưa được chẩn đoán có thể làm throughput và latency tệ đi.

## 17. Java 21+ virtual threads và cách tránh kết luận sai

Từ Java 21, **virtual threads** trở thành tính năng chuẩn (JEP 444). Virtual threads của Java API không tương ứng 1:1 với một native OS thread trong suốt vòng đời: chúng có thể được mount/unmount trên **carrier platform threads**.

JEP 312 là **cơ chế HotSpot xử lý JavaThread/VM runtime**, nên đừng suy:

- “Một virtual thread tương ứng một handshake poll page riêng y hệt một OS thread”.
- “Có một triệu virtual threads thì VM phải handshake đồng thời một triệu kernel threads”.
- “Thread-local handshake là API public để suspend một virtual thread”.
- “Global safepoint không ảnh hưởng virtual-thread workloads”.

Các luồng carrier, heap roots, continuation stacks và runtime scheduler có những quy tắc an toàn riêng. Nếu nghiên cứu tác động handshake với virtual threads, cần đọc tài liệu và mã nguồn JVM **đúng JDK version**. Để học phạm vi cục bộ vs toàn cục của JEP 312, hãy dùng mô hình JavaThreads/HotSpot trước khi áp ra hệ virtual threads.

## 18. Thí nghiệm performance: đánh giá đúng lợi ích của local coordination

Một test có hai luồng trong vài mili-giây **không đủ** để đo JVM handshake improvements. Phân tích performance có trách nhiệm cần:

1. Chốt JDK build/vendor và VM flags.
2. Dùng workload thật hoặc workload có stress phù hợp.
3. Xác định operation đang quan tâm có **thực sự dùng thread-local handshake** trên JDK đó không.
4. Không giả định Java public API tương đương một internal handshake.
5. Đo global safepoint count và các thời lượng; dùng JFR/`-Xlog:safepoint`.
6. Đo throughput/latency application, nhất là p95/p99.
7. Xem số platform JavaThreads, thời gian ở JNI/native và độ bận CPU.
8. Ghi GC type/heap, JIT, allocation rate, class loading và thread dumps liên quan.
9. So các cấu hình có cùng CPU/memory resources và IO load.
10. Lặp nhiều lần, xem distributions thay vì một số thời gian “đẹp”.
11. Phân biệt giảm **time-to-safepoint** với giảm **VM operation duration**.
12. Kiểm các tác động phụ: CPU overhead của nhiều local callbacks/diagnostics.
13. Không tự bật cờ JVM experimental/removed chỉ để kỳ vọng local handshake.
14. Báo rõ giới hạn: kết quả một JDK không tự đúng trên mọi JVM implementation.

### 18.1. Ví dụ giả định về scope

Giả sử có 500 platform threads, một operation chỉ cần kiểm trạng thái thread số 7:

~~~text
Trước khi có cơ chế cục bộ phù hợp:
  có thể cần phối hợp hàng trăm threads qua global safepoint

Với JEP 312 khi operation đủ điều kiện:
  yêu cầu handshake cho thread 7;
  các threads còn lại không phải target của operation này
~~~

Đây là minh họa **về phạm vi**, không phải số đo giảm 500 lần. Nếu thread 7 đang ở vị trí không an toàn hoặc operation bị nghẽn bởi lock, handshake vẫn có thể chậm. Nếu operation thực sự đòi toàn heap đồng bộ, global safepoint vẫn có thể là phương án đúng.

## 19. Tình huống triển khai: thread dump, GC và giám sát dịch vụ

### Tình huống A – Điều tra một thread có stack nghi vấn

Một profiler/serviceability tool có thể cần thông tin của một platform JavaThread. Thread-local handshakes cho JVM một cơ chế khả dụng để phối hợp riêng thread đó ở các đường nội bộ phù hợp. Nhưng **không tuyên bố** một Java API cụ thể luôn dùng handshake; điều đó thuộc implementation.

Thao tác đề xuất:

1. Dùng công cụ diagnostic/public API được hỗ trợ.
2. Kiểm runtime JDK version.
3. Xác minh collector/profiler/VM operation có ảnh hưởng toàn cục không.
4. Đo overhead nếu sampling tần suất cao.
5. Không dùng `Thread.suspend`/`stop` để “đóng băng” target cho việc đọc stack.

### Tình huống B – Log xuất hiện `Safepoint "G1CollectFull"`

Đây là event về **global safepoint/Full GC**, không phải bằng chứng handshake trên một thread. Cần:

1. Xác định nguyên nhân Full GC và thời lượng STW.
2. Kiểm heap occupancy, allocation rate, pause logs.
3. Không kỳ vọng JEP 312 tự xử lý Full GC mà không dừng mutators.
4. Tối ưu nguyên nhân GC pressure hoặc cân nhắc collector/heap sizing theo mục tiêu ứng dụng.
5. So latency business với events GC đã ghi.

### Tình huống C – Ứng dụng có rất nhiều threads nhưng safepoint latency cao

Số lượng threads là một yếu tố nhưng chưa đủ. Hãy kiểm time-to-safepoint, native states, monitor contention, OS scheduling, GC work và VM operations. Cơ chế cục bộ có lợi khi operation **không cần** toàn cục; nếu operation thật cần global safepoint, chỉ tăng hoặc giảm số threads ứng dụng không tự loại bỏ yêu cầu đó.

### Tình huống D – Tối ưu profiling và stack sampling

Công cụ modern profiler có thể dùng nhiều công nghệ: JVMTI, JFR, AsyncGetCallTrace/AsyncGetStackTrace tùy runtime, thread-local protocol, native sampling. Không phải tất cả sampling đều có cùng mức precision hoặc pause impact. Chọn công cụ theo mục tiêu và tài liệu hiện hành; kiểm data correctness/overhead trong môi trường sản xuất.

### Tình huống E – Đọc số lượng handshake log

Nếu `-Xlog:handshake=debug` không xuất bất kỳ event:

- Có thể workload không kích hoạt log tương ứng;
- Có thể level tag chưa đủ;
- Có thể thao tác diễn ra theo đường không được log ở version hiện tại;
- Có thể chưa dùng code path tạo handshake.

**Không** kết luận tính năng JEP 312 bị disable chỉ từ 0 dòng log. Ngược lại, thấy log handshake không chứng minh ứng dụng hoàn toàn không có STW events khác.

## 20. Các lỗi suy luận thường gặp

| Nhận định sai | Vì sao sai | Cách hiểu đúng |
| --- | --- | --- |
| “Handshake cục bộ dừng tất cả Java threads” | Phạm vi có thể chỉ là một JavaThread | Chỉ targets cần phối hợp |
| “Global safepoint là phải stop tất cả OS native threads” | Các threads native/VM có quy tắc khác | STW chủ yếu chặn Java mutator execution |
| “JEP 312 loại bỏ global safepoints” | Một số VM/GC operations vẫn đòi toàn cục | Handshakes chỉ thay những trường hợp phù hợp |
| “Handshake callback chắc chắn chạy trên target” | VM thread có thể xử lý thay khi an toàn | Self/VM-thread paths |
| “Chỉ cần gọi `Thread.interrupt` là handshake” | Interrupt là Java cooperation primitive | Khác internal HotSpot protocol |
| “`ThreadLocal` dùng để bật thread-local handshakes” | ThreadLocal chỉ lưu dữ liệu theo thread | Không liên quan trực tiếp JEP 312 |
| “All-thread handshake bằng global safepoint” | Targets có thể xử lý và tiếp tục độc lập | Không cần một global barrier cho cùng một điểm thời gian |
| “All-thread handshake cho atomic snapshot” | Callback có thể tại những thời điểm khác nhau | Cần synchronization/protocol snapshot riêng |
| “Handshake luôn instant” | Cần safepoint-safe state/polls, scheduler | Không có hard real-time guarantee |
| “Non-target threads không bao giờ pause” | Vẫn có locks/GC/scheduler/IO | Không bị handshake tự buộc dừng |
| “Nếu G1 Full GC vẫn STW thì JEP 312 bị hỏng” | Full GC có phạm vi global khác | Cả hai cơ chế có thể cùng tồn tại |
| “JEP 307 và 312 là cùng một cải tiến” | JEP 307 song song Full GC, JEP 312 handshake cục bộ | Phân biệt thuật toán GC và coordination scope |
| “Mọi Java stack trace API chắc chắn dùng handshake” | Implementation phụ thuộc JDK/tool | Không đoán từ public method name |
| “Thread WAITING luôn là JVM safepoint” | Java state khác VM safe state | Đọc đúng khái niệm |
| “Bị delay đến poll nghĩa thread bị lỗi” | Delay có thể hợp lệ theo code path/JNI/OS | Phân tích state và safepoint timings |
| “Log không có handshake tức tính năng không tồn tại” | Log coverage/tag/level không hoàn chỉnh | Xem JDK source/docs |
| “Global safepoint count bằng Full GC count” | Safepoints có nhiều nguyên nhân | Phân loại event cause |
| “Benchmark two-latch chứng minh HotSpot JEP 312 nhanh” | Latches chỉ mô hình application-level | Demo minh họa phạm vi, không benchmark VM |
| “Virtual thread = mỗi OS JavaThread” | Virtual threads có carriers | Không áp mô hình 1:1 |
| “Tắt biased locking để kích handshake” | Biased locking không còn là tối ưu hiện hành | Chỉ đọc như lịch sử, không dùng flags cũ |

## 21. Bài tập tự kiểm tra có đáp án

**Bài 1.** JEP nào bổ sung thread-local handshakes ở Java 10?

**Đáp án:** **JEP 312 – Thread-Local Handshakes**.

**Bài 2.** Handshake cho một thread B có bắt buộc A và C dừng Java execution không?

**Đáp án:** Không; operation chỉ cần phối hợp B. A/C có thể tiếp tục, trừ các nguyên nhân độc lập như GC STW, scheduler hoặc locks.

**Bài 3.** Global safepoint có nghĩa tất cả native OS threads ngừng tuyệt đối không?

**Đáp án:** Không. VM/GC/non-Java threads có thể tiếp tục; Java threads ở native/JNI state có quy tắc đặc biệt. Mục tiêu là giữ Java mutators trong trạng thái an toàn toàn VM.

**Bài 4.** Callback handshake chỉ có thể chạy trên chính target JavaThread?

**Đáp án:** Không. JEP mô tả target tự xử lý hoặc VM thread thực hiện thay trong trạng thái target đủ an toàn.

**Bài 5.** Vì sao callback không nên chạy tùy ý khi target đang chỉnh stack?

**Đáp án:** Vì references/registers/GC roots có thể thay đổi; VM cần safepoint-safe state để giữ invariants.

**Bài 6.** Một thread bị `WAITING` là đã thực hiện handshake chưa?

**Đáp án:** Không. `WAITING` là Java-level state, không chứng minh có pending/completed HotSpot handshake.

**Bài 7.** All-thread handshake có tự tạo snapshot atomic cho mọi thread không?

**Đáp án:** Không. Các callbacks có thể diễn ra ở thời điểm khác nhau và từng thread tiếp tục độc lập.

**Bài 8.** Vì sao Global safepoint có thể chậm khi một thread chưa an toàn?

**Đáp án:** Vì VM phải đợi các JavaThreads cần thiết đạt trạng thái safepoint-safe trước khi làm operation toàn cục.

**Bài 9.** Có Java SE public API `Thread.handshake` không?

**Đáp án:** Không. JEP 312 là cơ chế nội bộ HotSpot.

**Bài 10.** `Thread.interrupt()` có thay thế handshake JVM không?

**Đáp án:** Không. Interrupt là tín hiệu hợp tác ở application level; không mang invariants an toàn VM như handshake.

**Bài 11.** `ThreadLocal` có dùng để gọi JEP 312 không?

**Đáp án:** Không. `ThreadLocal` dành cho dữ liệu riêng theo Java thread.

**Bài 12.** Vì sao vẫn có `Pause Full` sau Java 10?

**Đáp án:** Vì một số GC operations cần global synchronization/STW; JEP 312 không loại bỏ chúng.

**Bài 13.** JEP 307 và JEP 312 khác nhau ở điểm nào?

**Đáp án:** JEP 307 song song hóa fallback G1 Full GC nhưng vẫn STW. JEP 312 cho phép JVM xử lý callback với phạm vi thread-local thay vì global safepoint khi đủ điều kiện.

**Bài 14.** Demo in `other-progressed=true` chứng minh điều gì?

**Đáp án:** Trong mô hình **application-level**, worker other đã hoàn thành job trong lúc target bị giữ ở latch. Không phải bằng chứng VM đã gọi internal handshake.

**Bài 15.** `tasks-before-release=0` có chứng minh cả JVM STW không?

**Đáp án:** Không. Hai demo workers đang ở barrier, main thread vẫn chạy; khác global safepoint thật.

**Bài 16.** Event `Safepoint "G1CollectFull"` trong vm.log là gì?

**Đáp án:** Một global safepoint thực trong HotSpot liên quan thao tác G1 Full GC ở cấu hình kiểm thử; không phải event handshake do application trực tiếp phát.

**Bài 17.** Không có dòng `handshake` ở debug log có chứng minh JEP 312 bị tắt không?

**Đáp án:** Không. Cần xét code path, log tags/levels và JDK version; internal handshake không bắt buộc in dòng cho mọi sự kiện.

**Bài 18.** Vì sao thread-local handshake không phải “miễn phí”?

**Đáp án:** Vẫn có chi phí điều phối, polling, callback và có thể chờ target đạt safepoint-safe state.

**Bài 19.** Nếu non-target A bị kẹt lock do B nắm, handshake cho B có bảo đảm A tiếp tục ngay không?

**Đáp án:** Không. A không bị handshake yêu cầu dừng, nhưng vẫn phụ thuộc lock contention đang có.

**Bài 20.** Dùng `Thread.stop` để giả lập việc dừng mục tiêu có an toàn không?

**Đáp án:** Không. Các APIs stop/suspend/resume đã bị deprecated/removed hoặc không được khuyến nghị vì vi phạm invariants; dùng cơ chế hợp tác và public concurrent APIs hiện hành.

**Bài 21.** Virtual threads từ Java 21 có ứng với mỗi OS thread riêng không?

**Đáp án:** Không. Chúng được scheduler mount lên carrier platform threads; không suy một virtual thread tương ứng một HotSpot JavaThread độc lập trong mọi trạng thái.

**Bài 22.** Khi nghiên cứu latency, có nên chỉ đo thời gian một GC event không?

**Đáp án:** Không. Phải tách time-to-safepoint, at-safepoint time, GC causes, application latency, CPU scheduling và workload khác.

**Bài 23.** Khi nào nên dùng global safepoint thay vì per-thread handshake?

**Đáp án:** Khi operation thật sự cần invariants/consistency toàn JVM trong một khoảng mà per-thread snapshots không bảo đảm.

**Bài 24.** JEP 312 có buộc developer sửa `Runnable`/`Executor` code không?

**Đáp án:** Không. Nó là cơ chế VM nội bộ; ứng dụng không phải trực tiếp tích hợp để nhận những cải thiện mà runtime sử dụng.

## 22. Checklist áp dụng khi đọc log hoặc phân tích JVM

1. **Đang phân tích JVM nào?** HotSpot/OpenJDK version/vendor/flags cụ thể?
2. **Operation có thật sự cần dừng toàn VM không?** Nếu không, có thể có local coordination.
3. **Là một thread, nhiều threads hay global synchronization?**
4. **Có nhầm all-thread handshake với global safepoint không?**
5. **Các callback được thực hiện trong safe state chưa?** Không đoán stack có thể đọc tùy ý.
6. **Có phân biệt Java-level WAITING với VM safepoint-safe không?**
7. **Có phân biệt JVM internal handshake với Java interrupt/latch/ThreadLocal không?**
8. **Có dùng nguồn chính thức JEP 312 thay vì mẹo cờ JVM cũ không?**
9. **Có log safepoint cause/time trên đúng JDK target không?**
10. **Có biết event handshake có thể không được log ở level đang bật không?**
11. **Có tính time-to-safepoint và at-safepoint riêng khi điều tra latency không?**
12. **Có kiểm GC collector/Full GC events tách khỏi những safepoints khác không?**
13. **Có nhìn global latency cùng request p95/p99 không?**
14. **Có tránh dự đoán speedup chỉ từ số thread không?**
15. **Có kiểm JNI/native code, OS scheduling và lock contention không?**
16. **Có hiểu per-thread observation không bảo đảm global atomic snapshot không?**
17. **Có tránh Thread.stop/suspend/resume và những thủ thuật không được hỗ trợ không?**
18. **Có xác định platform vs virtual threads khi áp ra JDK 21+ không?**
19. **Có dùng diagnostics với logging overhead/rotation phù hợp không?**
20. **Có giữ demo scope tách khỏi thực nghiệm của JVM nội bộ không?**
21. **Có so đúng runtime/build/VM flags nếu benchmark trước-sau không?**
22. **Có lập báo cáo nêu rõ đâu là spec/JEP, đâu là quan sát môi trường, đâu là giả định không?**

## 23. Tài liệu chính thức và nguồn tham khảo còn áp dụng

1. [OpenJDK JEP 312 – Thread-Local Handshakes](https://openjdk.org/jeps/312): định nghĩa mục tiêu Java 10, callback trên JavaThread ở trạng thái an toàn, và cơ chế tránh global VM safepoint trong những trường hợp phù hợp.
2. [Oracle – Introducing Java SE 10](https://blogs.oracle.com/java/introducing-java-se-10): danh sách JEP Java 10 bao gồm JEP 312 và mô tả callback không phải global safepoint.
3. [OpenJDK – HotSpot Handshake source (`handshake.hpp`)](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/handshake.hpp): cách trình bày cấu trúc handshake trong JDK hiện hành; nội bộ VM có thể thay đổi theo release.
4. [OpenJDK – HotSpot Handshake implementation (`handshake.cpp`)](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/handshake.cpp): implementation path của VM internals, chỉ để hiểu cơ chế chứ không phải Java public API.
5. [OpenJDK – Safepoint implementation (`safepoint.cpp`)](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/safepoint.cpp): logic global safepoint và thread-state handling của HotSpot hiện đại.
6. [Oracle Java SE 17 – java launcher / Unified JVM Logging](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `-Xlog`, log tags/levels/file syntax và tác động cấu hình Java launcher.
7. [Oracle Java SE 25 – java launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): thông tin hiện hành về logging/VM flags trên JDK hiện đại.
8. [Oracle Java SE 17 – Java Flight Recorder CLI](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): `jfr print` và xem events trong recording.
9. [Oracle Java SE 17 – jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): VM diagnostics và start/dump JFR khi JVM cho phép.
10. [Oracle Java SE 17 – Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): APIs public về lifecycle/interrupt/join, phân biệt với internal handshakes.
11. [Oracle Java SE 17 – ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): public thread diagnostics, không quy định phải dùng một VM handshake implementation cụ thể.
12. [Oracle Java SE 17 – CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): demo cooperative synchronization và memory consistency tại application level.
13. [OpenJDK JEP 444 – Virtual Threads](https://openjdk.org/jeps/444): mô hình virtual/platform threads từ Java 21, giúp tránh suy 1:1 OS-thread trong việc diễn giải JEP 312.
14. [OpenJDK HotSpot JFokus – Handshaking Design](https://cr.openjdk.org/~rehn/jfokus2020/JFokus-2020-HotSpot-Handshaking-v5.pdf): slide từ các tác giả HotSpot giải thích self-processing, VM-thread processing và per-thread callback.
15. [OpenJDK – Historical Handshake header design](https://cr.openjdk.org/~rehn/8185640/v10/Coleen-n-Test-Cleanup-4/webrev/src/hotspot/share/runtime/handshake.hpp.sdiff.html): mô tả rõ callback chỉ được gọi khi JavaThread safepoint-safe và có thể do target hoặc VM thread thực hiện.

**Tóm tắt:** **Thread-local handshakes** (JEP 312, Java 10) cho phép HotSpot phối hợp một hoặc nhiều JavaThreads **riêng lẻ**, xử lý callbacks khi chúng ở trạng thái **safepoint-safe**, không nhất thiết dừng tất cả threads. **Global safepoint** vẫn cần thiết cho operations yêu cầu global consistency, bao gồm một số GC pauses. **All-thread handshakes** không mặc nhiên là global STW, vì các callbacks có thể xử lý tại các thời điểm khác nhau và từng thread tiếp tục độc lập. Đây là **cơ chế nội bộ HotSpot**, không phải public Java API; dùng Java concurrency primitives chỉ như ví dụ về **phạm vi** và dùng `-Xlog:safepoint`/JFR để điều tra global safepoints trong VM thực tế.
