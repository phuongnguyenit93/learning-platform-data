# Điểm thực thi an toàn và sự phối hợp của luồng đích trong Thread-Local Handshakes (Java 10+)

## 1. Bản chất vấn đề

Một số thao tác bên trong **HotSpot JVM** cần quan sát hoặc xử lý trạng thái của **một Java thread cụ thể** trong một thời điểm mà JVM biết rằng cấu trúc thực thi của luồng đó đủ ổn định. Ví dụ, khi một công cụ chẩn đoán cần lấy stack trace của một luồng đang chạy, việc đọc tùy tiện trong lúc các frame và thanh ghi của luồng đó đang thay đổi có thể không an toàn.

Trước khi có cơ chế **Thread-Local Handshakes**, nhiều thao tác kiểu này cần đưa các Java threads về một **global safepoint**: toàn bộ luồng Java được phối hợp về trạng thái có thể được JVM quan sát an toàn. Chi phí đáng kể là những luồng **không liên quan** cũng bị ảnh hưởng.

**JEP 312 — Thread-Local Handshakes**, được triển khai trong **Java 10**, đưa vào cơ chế để JVM có thể yêu cầu một callback (*handshake operation*) đối với **luồng đích**, mà **không bắt buộc** tạo global safepoint chỉ để thực hiện thao tác đó.

Tư tưởng cốt lõi:

> JVM phối hợp với luồng đích, chờ hoặc xác nhận một trạng thái **safepoint-safe**, thực hiện thao tác tương ứng, rồi cho luồng đích tiếp tục. Những luồng không liên quan không cần phải dừng cùng lúc **chỉ vì handshake này**.

Cơ chế không phải một API lập trình ứng dụng mới như `Thread.handshake()`; nó là **hạ tầng nội bộ của HotSpot**. Các API công khai (chẳng hạn `Thread.getStackTrace()`) hoặc công cụ như JVMTI/JFR có thể được JVM triển khai dựa trên hạ tầng đó, nhưng cách mỗi API được hiện thực có thể thay đổi theo phiên bản JVM.

### Tóm tắt qua hai hình dung

**Global safepoint:**

```text
VM yêu cầu trạng thái an toàn toàn cục
                     |
Thread A:  chạy -> dừng an toàn ----------> tiếp tục
Thread B:  chạy -> dừng an toàn ----------> tiếp tục
Thread C:  chạy -> dừng an toàn ----------> tiếp tục
                     | JVM thực hiện công việc chung
                     v
              Kết thúc safepoint
```

**Thread-local handshake với B là luồng đích:**

```text
VM cần quan sát B
       |
A:  tiếp tục chạy bình thường (nếu không có lý do dừng khác)
B:  chạy -> điểm/trạng thái an toàn -> handshake -> chạy tiếp
C:  tiếp tục chạy bình thường (nếu không có lý do dừng khác)
       |
       +-- chỉ B cần phối hợp cho thao tác dành riêng B
```

Hình thứ hai là mô hình **khái niệm**, không phải cam kết mọi luồng khác luôn chạy không gián đoạn: scheduler, GC, đồng bộ hóa ứng dụng hoặc một VM operation **khác** vẫn có thể làm chúng bị trì hoãn.

## 2. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt **global safepoint** và **thread-local handshake**.
2. Giải thích “điểm thực thi an toàn” trong ngữ cảnh JVM khác gì `Thread.State.WAITING` hoặc `Thread.sleep()`.
3. Mô tả cách HotSpot chèn/kiểm tra **safepoint polls** trong mã interpreted và JIT-compiled.
4. Hiểu quá trình **yêu cầu → thông báo → đến trạng thái an toàn → xử lý → hoàn tất → tiếp tục**.
5. Phân biệt hai đường xử lý: **luồng đích tự thực thi callback** và **luồng hỗ trợ/đề nghị xử lý thay khi trạng thái đích đã an toàn**.
6. Hiểu vì sao không thể tự ý đọc/mutating stack đang chuyển động của luồng khác.
7. Xem xét các trạng thái đang chạy Java, bị chặn, đang ở native code và lúc chuyển trạng thái.
8. Phân biệt handshake safety với **Java Memory Model**, `volatile`, locks và `happens-before`.
9. Nhận diện `-Xlog:handshake=info`/`trace` và cách đọc log HotSpot hiện hành.
10. Chạy chương trình Java 17+ lấy stack trace từ luồng đang chạy và luồng đang chờ, quan sát hai đường xử lý trên JDK hỗ trợ.
11. Không suy luận một lần `Thread.getStackTrace()` luôn kích hoạt handshake ở mọi JVM.
12. Hiểu handshake không đồng nghĩa với real-time guarantee hoặc `Thread.interrupt()`.
13. Nhận diện giới hạn khi luồng ở JNI/native hoặc các điểm poll bị trì hoãn.
14. Phân biệt Java platform threads, `JavaThread` nội bộ và virtual threads.
15. Tránh dùng cờ nội bộ cũ hoặc legacy HotSpot options như một phần API ổn định.

## 3. “Safepoint-safe” là gì?

Ở mức JVM, một thao tác đụng đến stack, object references hoặc metadata có thể đòi hỏi trạng thái mà VM **biết cách diễn giải an toàn**. Ví dụ, compiler/JVM cần đủ metadata để xác định nơi lưu các object references trong register hoặc stack frame; một phép stack walk yêu cầu các frame ở trạng thái có thể được quan sát nhất quán theo cơ chế runtime.

Một luồng đang thi hành mã máy của JIT có thể thay đổi:

- Program counter.
- Các register chứa giá trị tạm.
- Frame layout/stack pointer.
- Object references trong register hoặc trên stack.
- Trạng thái chuyển từ Java sang VM/native và ngược lại.

Do đó, **không được xem mọi instruction boundary đều là thời điểm hợp lệ để VM thực hiện mọi callback**.

**Safepoint-safe** nghĩa là JVM đã đạt hoặc xác nhận một trạng thái **theo hợp đồng của cơ chế nội bộ**, sao cho thao tác được yêu cầu có thể thực hiện mà không vi phạm các invariant về trạng thái luồng.

Điều này **không đồng nghĩa**:

- Luồng Java đã gọi `Thread.yield()`.
- Luồng bắt buộc ở `Thread.State.WAITING`.
- Luồng đã thả mọi Java monitor.
- Luồng đang rảnh CPU.
- Mọi luồng Java khác đã dừng.
- Ứng dụng đã đạt một điểm nhất quán transaction.
- Người lập trình có thể an toàn ghi trực tiếp mọi trường của object thuộc luồng đích.

Phạm vi “an toàn” phụ thuộc vào **operation** và kiểm soát của VM, không phải một biến boolean mà ứng dụng tự quyết.

### Safepoint-safe khác một global safepoint

- **Safepoint-safe thread state:** trạng thái của một luồng đã được xác nhận phù hợp để thực hiện một thao tác VM cụ thể.
- **Global safepoint:** cơ chế JVM phối hợp **tất cả các Java threads liên quan** về trạng thái an toàn để thực hiện tác vụ toàn cục.
- **Thread-local handshake:** tận dụng trạng thái an toàn **ở luồng đích**, không phải luôn bắt mọi luồng khác cùng tham gia.

Một global safepoint có thể xảy ra đúng lúc ứng dụng đang dùng handshake, nhưng bản thân handshake **không ngụ ý** tạo global safepoint.

## 4. “Điểm kiểm tra” (*poll*) của HotSpot

Cách một luồng đang chạy Java nhận biết rằng VM cần phối hợp là thông qua **safepoint polling**. JVM có thể thiết kế các phép kiểm tra phù hợp vào những vị trí mà runtime biết cách xử lý an toàn, chẳng hạn:

- Các điểm quay lại/đầu vòng lặp (*loop backedges/headers*) trong mã JIT.
- Các điểm thoát hoặc chuyển tiếp phương thức theo chiến lược compiler.
- Các điểm trong mã interpreted, tương ứng với hoạt động dispatch/nhánh/return.
- Những **state transitions** giữa Java, VM và native cần kiểm tra tình trạng safepoint/handshake trước khi tiếp tục chạy Java.

Đây là **ví dụ cơ chế**, không phải cam kết rằng mọi Java statement, every bytecode hoặc mọi iteration có một poll riêng. Vị trí poll phụ thuộc interpreter, compiler tier, CPU architecture, tối ưu hóa, bản JDK và loại method.

JEP 312 cho phép quản lý yêu cầu handshake theo **mức từng luồng**: thay vì chỉ một cơ chế “global poll” cho mọi JavaThread, VM có thể đánh dấu/yêu cầu một luồng đích cụ thể đáp ứng.

```text
Mã Java / JIT code của thread B

  [thực thi] -> [thực thi] -> [điểm poll] -> [thực thi]
                                  |
                         Có pending handshake?
                           /           \
                         Không         Có
                          |             |
                     tiếp tục       vào VM handler
                                      |
                               safepoint-safe state
                                      |
                                 xử lý operation
                                      |
                                 tiếp tục chạy
```

Một poll hoạt động như **điểm hợp tác do runtime chèn/kiểm soát**, không phải một lệnh ứng dụng `if (handshakeRequested)`.

## 5. Tại sao phải để luồng đích phối hợp?

Giả sử một tiến trình muốn xem stack của thread B trong khi B đang thực thi một vòng lặp được JIT tối ưu hóa. Nếu thread khác tự tiện đọc stack/PC/registers của B, có thể thấy một tổ hợp dữ liệu không nhất quán hoặc không đủ metadata để giải mã frame.

Trong handshake:

1. **B được xác định** là thread cần quan sát hoặc thao tác.
2. Một yêu cầu VM được gắn vào trạng thái handshake dành cho B.
3. VM sắp xếp để B **nhận ra yêu cầu** ở điểm poll hoặc trạng thái/chuyển trạng thái phù hợp.
4. Thao tác chỉ được thực hiện khi B ở **safepoint-safe state**.
5. Việc thực hiện được **phối hợp để tránh cả B và luồng hỗ trợ cùng chạy callback hai lần**.
6. Yêu cầu được đánh dấu hoàn thành và B tiếp tục.

Luồng B không phải “đồng ý” bằng một lời gọi ứng dụng công khai; sự hợp tác nằm trong cơ chế interpreter, JIT và VM state transitions.

### Hợp tác không đồng nghĩa phải chờ B tự làm mọi thứ

Nếu B đang **bị chặn** trong một trạng thái mà VM có thể xác minh là an toàn, một thread xử lý handshake ở phía VM có thể thực hiện callback **thay cho B**, trong lúc B vẫn bị chặn. Nhờ đó không cần đánh thức B lên chạy Java code chỉ để thực hiện một stack observation.

Cơ chế đã tồn tại từ thiết kế JEP 312 và tiếp tục được phát triển; chính xác thread nào thực hiện thay có thể là VM/service/requesting JavaThread tùy đường xử lý và phiên bản HotSpot. **Không đóng đinh mọi trường hợp chỉ do VMThread thực hiện.**

## 6. Vòng đời của một thao tác thread-local handshake

Có thể mô tả luồng phối hợp tổng quát:

```text
   [Requester / subsystem JVM]
               |
      1. Chọn target B
               |
      2. Enqueue/đăng ký
         handshake operation
               |
      3. Arm poll hoặc thiết lập
         tín hiệu cho target B
               |
           +---+-------------------------+
           |                             |
    B đang chạy Java             B đang ở state an toàn
           |                             |
  4a. B gặp safepoint poll       4b. VM xác minh state ổn định
           |                             |
  5a. B xử lý "by self"          5b. helper/requester xử lý
           |                             |
           +-------------+---------------+
                         |
                6. Callback hoàn tất
                   + cập nhật trạng thái
                         |
                7. Disarm/clear yêu cầu
                         |
            8. B tiếp tục hoặc giữ trạng thái
               blocked vốn có của ứng dụng
                         |
               Requester nhận hoàn tất
                (nếu là sync handshake)
```

**Không xem đây là một implementation spec bất biến**: nội bộ HotSpot có các operation đồng bộ/bất đồng bộ, queue, lock, bộ đếm và quy tắc vòng đời thread có thể thay đổi theo bản JDK. Sơ đồ chỉ thể hiện invariant cốt lõi: **bảo đảm thao tác được xử lý trong điều kiện an toàn cho thread được nhắm tới, không thực thi trùng do race**.

### Vì sao phải “arm” rồi “disarm”?

Đây là cơ chế cho VM biết có việc cần phục vụ ở poll tương ứng. Sau khi operation đã được xử lý và không còn yêu cầu, VM có thể bỏ tín hiệu. Nếu không có bước quản lý trạng thái này, luồng có thể bị kiểm tra hoặc đi vào handler không cần thiết, hoặc requester có thể hiểu sai là handshake đã xong.

### Handshake không thay Java scheduler

VM **không hứa** thread B sẽ được CPU ngay lập tức. Nếu B chưa được scheduler cho chạy, hoặc đang ở đoạn runtime/native không sẵn sàng, completion có thể phải chờ. Thread-local handshakes giảm nhu cầu dừng không liên quan, **không bảo đảm deadline cố định**.

## 7. Đường xử lý thứ nhất: luồng đích tự thực hiện (*by self*)

Khi B đang chạy mã Java và gặp poll đã được arm:

1. JVM chuyển B tới đoạn xử lý handshake thích hợp.
2. B đi vào trạng thái VM an toàn cho callback.
3. B thực hiện operation của chính nó.
4. B thông báo hoàn tất và trở lại việc đang làm.

```text
Thread B (target)

while (đang chạy mã Java) {
    [JIT/interpreter work]
    [poll đã arm] --------------------+
                                     |
                              handshake handler
                                     |
                                callback(B)
                                     |
                              clear/complete
                                     |
                             resume Java work
}
```

**Đây là mã giả, không phải Java code có API `callback(B)`.** JVM quyết định cách chèn poll, cách giữ stack ở trạng thái an toàn và cách xử lý.

### Quan sát bằng HotSpot logging

Ở JDK 24 được thử nghiệm, việc gọi `target.getStackTrace()` nhiều lần từ thread chính trong lúc target đang chạy tạo log dạng:

```text
[...][trace][handshake] Proc handshake synchronous ... by self
[...][info ][handshake] Handshake "GetStackTraceClosure",
    Targeted threads: 1, Executed by requesting thread: 0,
    Total completion time: ... ns
```

Cần hiểu:

- `GetStackTraceClosure` là **tên callback nội bộ** trong bản HotSpot quan sát được.
- `Targeted threads: 1`: handshake nhắm vào một target.
- `Executed by requesting thread: 0` trong lần thử: không có operation nào được requester thực hiện thay; target **tự phục vụ**.
- `... ns` là thời gian completion đo được **một lần**, không phải chỉ tiêu cố định.
- Dạng log/đếm và lựa chọn đường xử lý không phải cam kết Java SE API.

Đừng tự suy luận từ `Thread.getStackTrace()` rằng JVM **luôn** phải dùng handshake; đây là ví dụ cách HotSpot hiện tại sử dụng cơ sở hạ tầng ấy.

## 8. Đường xử lý thứ hai: luồng hỗ trợ xử lý khi target bị chặn

Một target có thể đang chờ `CountDownLatch.await()`, Java monitor, park hoặc một tình huống blocked/transition khác. Không phải lúc nào target cũng đang tự chạy mã Java để tiến đến poll.

Nếu JVM xác minh target đang ở một trạng thái **handshake-safe ổn định**, một phía **helper/handshaker** có thể nhận và thực hiện callback thay:

```text
Thread B / blocked-target: [await ... vẫn đang chờ]
                                  |
Requester/VM:         [kiểm tra B safe?]
                                  |
                     [giữ ổn định trạng thái B]
                                  |
                     [thực hiện callback cho B]
                                  |
                     [đánh dấu đã hoàn tất]
                                  |
Thread B:             [vẫn chờ latch như trước]
```

Điều này **không** biến luồng B thành runnable và **không** yêu cầu nó hoàn thành `await()`.

Trong lab JDK 24, `blocked.getStackTrace()` cho log:

```text
[...][trace][handshake] Processing handshake ... by handshaker(JavaThread)
[...][info ][handshake] Handshake "GetStackTraceClosure",
    Targeted threads: 1, Executed by requesting thread: 1,
    Total completion time: ... ns
```

Dấu `1` là số operation trong trường log được xử lý bởi requesting thread; **không phải ID của Java thread** và cũng không phải bằng chứng rằng mọi HotSpot version chỉ cho requester xử lý.

### Vì sao phải xác minh trạng thái ổn định?

Một target **có thể đang chuyển từ blocked sang runnable**. Nếu requester chỉ đọc một cờ trạng thái rồi lập tức xử lý stack B, B có thể tiếp tục chạy và thay đổi frame cùng lúc. HotSpot dùng giao thức đồng bộ nội bộ để tránh **race giữa target tự xử lý và helper xử lý**.

Về nguyên tắc:

- Một bên phải **claim** operation theo quy tắc đồng bộ phù hợp.
- Target hoặc helper có thể xử lý khi các điều kiện an toàn còn đúng.
- Bên còn lại không được thực thi cùng callback một lần nữa.
- Khi operation hoàn tất, trạng thái pending được cập nhật chính xác.

Không dùng `Thread.State.WAITING` như **bằng chứng đủ** để truy cập stack theo kiểu native/Unsafe từ ứng dụng. `Thread.getState()` chỉ là ảnh chụp ở cấp Java và bản thân cũng có thể đổi sau khi đọc.

## 9. So sánh hai đường thực thi

| Tình huống | Target có thể tự xử lý? | Có thể cần helper? | Điều kiện cốt lõi |
| --- | --- | --- | --- |
| Target đang chạy Java và tiến đến safepoint poll | **Có** | Có thể tùy race/triển khai | Handler đưa target vào trạng thái an toàn |
| Target đang chờ trên monitor/latch/park | Không nhất thiết đang chạy | **Có thể** | VM xác nhận trạng thái blocked ổn định và an toàn |
| Target đang trong native code | Phụ thuộc transition | **Có thể** nếu đủ điều kiện | State/stack anchor có thể được xác minh safe |
| Target đang chuyển state | Có thể phải chờ | Không tùy tiện xử lý | Tránh xem transition chưa ổn định là an toàn |
| Target đã kết thúc | Không còn chạy Java | JVM xử lý life cycle theo hợp đồng | Không dereference JavaThread đã giải phóng |
| Nhiều targets | Mỗi target cần được xử lý phù hợp | Tùy implementation và loại operation | Không mặc định tạo global pause |

Bảng mang ý nghĩa **khả năng**, không phải một quy tắc máy móc “Thread.State.X luôn được helper xử lý”.

### Tại sao không cần dừng những thread khác?

Vì **yêu cầu** nhắm tới một hoặc một nhóm thread cụ thể. Nếu target B đã safe và callback chỉ cần trạng thái B, VM không nhất thiết chờ toàn bộ A/C/D đạt safepoint.

Nếu JVM **đồng thời** có hoạt động GC toàn cục, class redefinition hoặc tác vụ yêu cầu global safepoint, các thread không liên quan có thể dừng bởi **tác vụ đó**. Không được khẳng định “trong lúc handshake thì không bao giờ có bất kỳ global pause nào”.

## 10. Safepoint polling không phải `Thread.sleep`, `yield` hay `onSpinWait`

Một lỗi phổ biến là nghĩ ứng dụng có thể “chỉ định điểm handshake” bằng:

```java
Thread.yield();
Thread.sleep(1);
Thread.onSpinWait();
```

**Không đúng.**

- `Thread.yield()` là lời gợi ý scheduler về việc nhường CPU.
- `Thread.sleep(...)` là yêu cầu ngủ trong một khoảng thời gian, không cam kết đúng giờ và còn chịu interrupt.
- `Thread.onSpinWait()` là CPU/JVM hint cho một vòng lặp chờ chủ động.

Chúng **không phải API tạo handshake operation**, cũng không bảo đảm “ngay khi gọi dòng này, pending handshake được xử lý”.

HotSpot tự chèn safepoint polls ở những điểm nội bộ phù hợp; ví dụ chạy vòng lặp có `onSpinWait()` chỉ giúp mô hình busy thread có hoạt động rõ ràng, chứ không “gửi handshake”.

### `synchronized` và monitor

Một luồng đang chờ monitor có thể được JVM xem xét an toàn cho một operation cụ thể, nhưng điều đó không có nghĩa mọi stack operation của người dùng được phép can thiệp vào monitor. JVM quản lý nội bộ sự tương tác này; **Java code vẫn phải tuân thủ khóa, visibility và thread-safety bình thường**.

### `Thread.interrupt()`

`interrupt()` đặt interrupt status và tác động lên một số blocking operations. Nó **không** là lời gọi yêu cầu JVM thực thi `HandshakeClosure` của JEP 312. Nếu muốn dừng một worker theo thiết kế ứng dụng, dùng cancellation/interrupt/flag theo hợp đồng, không trông chờ handshakes nội bộ.

## 11. Java thread ở native code và lúc chuyển trạng thái

Không phải mọi Java thread luôn ở trạng thái chạy bytecode hoặc compiled Java method.

Khi một luồng đi vào **native code/JNI**, trạng thái VM và khả năng đi dọc Java stack có quy tắc riêng. Trong một số tình huống, VM có thể xác minh trạng thái native là safe nếu không có Java frame hoặc stack anchor phù hợp để walk.

Nhưng **không** suy ra:

- “Cứ vào native là handshake thực hiện ngay lập tức.”
- “Mọi JNI call đều có thể bị chặn giữa bất kỳ machine instruction nào.”
- “Thread đang ở native thì JVM không cần kiểm tra gì khi trở lại Java.”
- “Có thể xử lý stack JNI bằng cách đọc dữ liệu object memory tùy tiện.”

Ở các state transitions, HotSpot bảo đảm những kiểm tra/thứ tự bộ nhớ cần thiết để luồng **không thoát sang trạng thái không an toàn** trong lúc thao tác VM dựa vào việc nó đang safe.

Một native call kéo dài hoặc ở critical region có thể làm latency của một operation bị trì hoãn. Handshake là **cơ chế an toàn**, không có hợp đồng thời gian tối đa để hoàn thành.

### Điểm an toàn không phải điểm mọi đối tượng bất biến

Đối tượng Java trên heap có thể vẫn được các luồng khác sửa. Safepoint-safe state chỉ nói điều kiện an toàn của **operation VM cụ thể trên target**, **không** bảo đảm dữ liệu ứng dụng toàn cục đạt nhất quán. Muốn snapshot nhất quán của một data structure do nhiều thread cập nhật, cần lock/atomicity/cơ chế riêng.

## 12. Handshake đồng bộ và bất đồng bộ

Không phải mọi handshake đều được gọi với cùng yêu cầu thời điểm hoàn tất.

**Synchronous handshake** theo nghĩa chung: requester cần biết operation đã được thực hiện/xử lý đủ trước khi tiếp tục công việc phụ thuộc vào nó.

**Asynchronous handshake**: VM có thể gửi một operation và tiếp tục xử lý những công việc khác mà không đợi callback hoàn tất ngay tại chỗ.

Nội bộ HotSpot hiện đại có nhiều lớp operation và đường lập lịch, tuy nhiên chi tiết **queue, type, ownership, cancellation, timeout, spin/yield** là implementation details. Không viết code Java dựa trên số lần poll hay thứ tự completion giả định.

Với một handshake nhắm tới **nhiều target**:

- Mỗi target phải đến trạng thái safe tương ứng.
- Các callback không nhất thiết chạy tại cùng thời điểm.
- Target nào xử lý xong có thể tiếp tục sớm hơn target khác theo triển khai/cấu hình.
- Không đồng nghĩa một **global barrier** cho toàn bộ Java threads.

**Câu chốt:** “Thread-local” nói về **mức độ nhắm đích của cơ chế**, không ngụ ý mọi callback luôn có thời gian hoàn thành bằng nhau.

## 13. Ứng dụng thực tế: lấy stack trace của một thread cụ thể

Một hoạt động dễ quan sát là **lấy stack trace của thread khác** qua API công khai:

```java
StackTraceElement[] trace = target.getStackTrace();
```

Từ phía Java, bạn nhận một mảng stack frames. Cơ chế **bên trong JVM** để thu thập có thể sử dụng per-thread handshake khi cần quan sát target an toàn, như đã được kiểm thử trên **HotSpot JDK 24.0.2**.

**Không được coi `getStackTrace()` là API “gửi handshake” được bảo đảm bởi Java SE.** Java API chỉ hứa các thuộc tính của việc lấy stack trace; HotSpot có quyền thay đổi cách hiện thực, và các JVM khác có thể xử lý khác.

Trong bài lab này, các thao tác:

```java
target.getStackTrace();
blocked.getStackTrace();
```

được dùng vì trên HotSpot JDK 24 chúng cho phép **quan sát handshake logs trực tiếp**. Đây là kỹ thuật học/diagnostics, không phải một cơ chế để ứng dụng “dừng chính xác thread B tại điểm an toàn đã chọn”.

### Stack trace không phải snapshot trạng thái kinh doanh

Một stack trace cho biết các phương thức/frame được quan sát tại một thời điểm. Nó **không** chứa đầy đủ các field/transactions, không bảo đảm một snapshot atomic trên nhiều luồng và không phải cách an toàn để trực tiếp can thiệp vào nội dung stack của một luồng khác.

Nếu muốn thu thập thông tin phục vụ vận hành, nên dùng API chẩn đoán chuẩn (`Thread.getStackTrace`, `ThreadMXBean`, `Thread.dumpStack` trong ngữ cảnh tương ứng), JFR hoặc jcmd theo yêu cầu. Không dùng các lớp `sun.*`/`jdk.internal.*` không được hỗ trợ như API ứng dụng.

## 14. Chương trình Java 17+ độc lập: target đang chạy và target đang chờ

Tạo tệp **`ThreadHandshakeSafetyDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

public final class ThreadHandshakeSafetyDemo {
    static void require(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        var running = new AtomicBoolean(true);
        var begun = new CountDownLatch(2);
        var targetTicks = new AtomicLong();
        var peerTicks = new AtomicLong();

        Thread target = new Thread(() -> {
            targetTicks.incrementAndGet();
            begun.countDown();
            while (running.get()) {
                targetTicks.incrementAndGet();
                Thread.onSpinWait();
            }
        }, "running-target");

        Thread peer = new Thread(() -> {
            peerTicks.incrementAndGet();
            begun.countDown();
            while (running.get()) {
                peerTicks.incrementAndGet();
                Thread.onSpinWait();
            }
        }, "unrelated-peer");

        target.start();
        peer.start();
        begun.await();

        boolean activeFramesPresent = true;
        try {
            for (int i = 0; i < 32; i++) {
                activeFramesPresent &= target.getStackTrace().length > 0;
            }
        } finally {
            running.set(false);
            target.join();
            peer.join();
        }

        var releaseBlocked = new CountDownLatch(1);
        var blockedStarted = new CountDownLatch(1);
        Thread blocked = new Thread(() -> {
            blockedStarted.countDown();
            try {
                releaseBlocked.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "blocked-target");

        blocked.start();
        blockedStarted.await();

        boolean wasWaiting = false;
        boolean blockedFramesPresent = true;
        try {
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
            while (System.nanoTime() < deadline) {
                if (blocked.getState() == Thread.State.WAITING) {
                    wasWaiting = true;
                    break;
                }
                Thread.onSpinWait();
            }
            require(wasWaiting, "target not WAITING");

            for (int i = 0; i < 12; i++) {
                blockedFramesPresent &= blocked.getStackTrace().length > 0;
            }
        } finally {
            releaseBlocked.countDown();
            blocked.join();
        }

        require(activeFramesPresent, "running target stacks missing");
        require(blockedFramesPresent, "blocked target stacks missing");

        System.out.println("runningSamples=32");
        System.out.println("runningStacksPresent=" + activeFramesPresent);
        System.out.println("runningTargetProgress=" + (targetTicks.get() > 0));
        System.out.println("unrelatedThreadProgress=" + (peerTicks.get() > 0));
        System.out.println("blockedReachedWaiting=" + wasWaiting);
        System.out.println("blockedSamples=12");
        System.out.println("blockedStacksPresent=" + blockedFramesPresent);
        System.out.println("allThreadsTerminated="
                + (!target.isAlive() && !peer.isAlive() && !blocked.isAlive()));
    }
}
```

### Cách hoạt động

**Giai đoạn 1 — target đang chạy:**

- `running-target` và `unrelated-peer` được khởi chạy.
- `CountDownLatch begun` chờ cả hai thread bước vào thân hàm.
- Trong vòng lặp, mỗi thread tăng một `AtomicLong` và dùng `onSpinWait` như một *spin-wait hint*.
- Thread `main` đọc `target.getStackTrace()` **32 lần**, trong lúc target còn chạy.
- `running.set(false)` và `join()` dừng có phối hợp, không sử dụng `Thread.stop()` hay busy waiting vô hạn.
- Các giá trị `targetTicks`/`peerTicks` được kiểm bằng điều kiện dương, **không** assert số vòng lặp chính xác theo scheduler.

**Giai đoạn 2 — target đang chờ:**

- `blocked-target` gọi `releaseBlocked.await()` và có state `WAITING` tại thời điểm được quan sát.
- Thread `main` chỉ có tối đa 3 giây để đợi state WAITING trong **môi trường lab**; nếu không thấy, chương trình báo lỗi rõ thay vì giả vờ kiểm thử thành công.
- Thread `main` lấy stack trace **12 lần** khi target chưa được giải phóng latch.
- `finally` giải phóng latch, sau đó `join()` để tránh bỏ lại background thread.

**Phần quan trọng:** hai giai đoạn tạo tình huống dễ quan sát, nhưng **không** biến `Thread.State.WAITING` thành API xác nhận handshake-safe hay mô tả bắt buộc quá trình bên trong VM.

### Lệnh biên dịch

```bash
javac --release 17 -encoding UTF-8 ThreadHandshakeSafetyDemo.java
```

Chạy bình thường:

```bash
java ThreadHandshakeSafetyDemo
```

**Stdout của chương trình:**

```text
runningSamples=32
runningStacksPresent=true
runningTargetProgress=true
unrelatedThreadProgress=true
blockedReachedWaiting=true
blockedSamples=12
blockedStacksPresent=true
allThreadsTerminated=true
```

Đây là stdout **đã được xác minh** trên bản HotSpot JDK 24. Chương trình không in actual thread IDs, thứ tự xuất hiện của log JVM, thời gian pause hay giá trị bộ đếm thay đổi theo scheduler.

### Phân tích output

- `runningSamples=32` và `blockedSamples=12` xác nhận số lần lấy stack trace mà code đã thực hiện.
- `runningStacksPresent=true` và `blockedStacksPresent=true` xác nhận target có frame trong các lần đọc đã chọn.
- `runningTargetProgress=true`: target đã thực thi code và tăng bộ đếm.
- `unrelatedThreadProgress=true`: luồng khác đã thực thi code. **Đây không phải bằng chứng toán học rằng peer chạy liên tục không dừng ở mọi nano-giây trong handshake.**
- `blockedReachedWaiting=true`: target đã ở state WAITING lúc quan sát, sau đó được giải phóng latch.
- `allThreadsTerminated=true`: cả ba worker threads đã kết thúc có kiểm soát.

Chương trình **không tự gọi một `Handshake` API công khai**, vì không có API Java SE như vậy. Phần chứng minh cơ chế nằm ở **HotSpot logs** sau khi bật logging.

## 15. Quan sát log handshake trên HotSpot

Trên các HotSpot JDK hỗ trợ Unified Logging tag `handshake`, chạy:

```bash
java -Xlog:handshake=trace ThreadHandshakeSafetyDemo
```

Log chứa nhiều thông tin nội bộ và có thể đan xen stdout. Để tách riêng:

```bash
java -Xlog:handshake=trace:file=handshake.log:uptime,level,tags \
     ThreadHandshakeSafetyDemo
```

PowerShell (một dòng):

```powershell
java "-Xlog:handshake=trace:file=handshake.log:uptime,level,tags" ThreadHandshakeSafetyDemo
```

**Kiểm tra tag được JVM hỗ trợ:**

```bash
java -Xlog:help
```

Tìm tên tag `handshake` trong danh sách; đó là tag HotSpot logging có trong runtime lab. Nếu runtime không hỗ trợ tag/log syntax hoặc không có event ứng với API, không tự kết luận rằng ứng dụng Java sai.

### Log quan sát được trong lab JDK 24

Với chương trình trên và đúng cấu hình logging:

```text
... Proc handshake synchronous ... by self
... Handshake "GetStackTraceClosure",
    Targeted threads: 1, Executed by requesting thread: 0,
    Total completion time: ... ns

... Processing handshake ... by handshaker(JavaThread)
... Handshake "GetStackTraceClosure",
    Targeted threads: 1, Executed by requesting thread: 1,
    Total completion time: ... ns
```

Hai nhóm minh họa:

- Luồng đang chạy: **32 operation** được log theo đường `by self`.
- Luồng đang chờ: **12 operation** được log như do **requesting thread** thực hiện.
- Cả hai đều nhắm **1 target** cho mỗi lời gọi được quan sát.

**Không được assert literal timestamp, memory addresses, thời lượng nanoseconds hoặc thứ tự toàn bộ logs.** Con số 32/12 thuộc **một lần chạy đã kiểm thử**; các JDK khác có thể dùng cơ chế khác, gộp events hoặc chọn đường self/helper khác dù cùng hành vi Java.

### Chú ý cách diễn giải log

`Executed by requesting thread: 1` **không** có nghĩa thread ID = 1. Đây là thống kê số handshake operations trong một event đã được requester xử lý thay. Log cũng có thể là một asynchronous event trong tình huống khác; không suy ngược tất cả các handshake của ứng dụng từ một dòng.

Để xem nhanh trên Linux/macOS:

```bash
grep -E 'GetStackTraceClosure|by self|by handshaker' handshake.log
```

PowerShell:

```powershell
Select-String -Path .\handshake.log -Pattern 'GetStackTraceClosure|by self|by handshaker'
```

Các lệnh trên chỉ lọc **log đã sinh**, không làm thay đổi Java source. Tránh để `handshake=trace` trong môi trường production lâu dài nếu log quá lớn/tiết lộ thông tin runtime hoặc tạo overhead không cần thiết.

## 16. Sự phối hợp an toàn tránh thực thi callback trùng lặp

Một race điển hình cần JVM phòng vệ:

1. Requester thấy target B đang blocked.
2. Nó cân nhắc thực hiện operation thay B.
3. Đúng lúc đó B thức dậy và đi tới safepoint poll.
4. **Cả hai bên** đều có thể phát hiện pending operation.

Nếu mỗi bên tự chạy callback mà không có giao thức đồng bộ, operation có thể bị thực thi **hai lần**, hoặc target tiếp tục trong lúc helper đang dựa vào state cũ.

HotSpot xử lý bằng trạng thái handshake và đồng bộ thích hợp (ownership/locking/claim/queue/counter theo triển khai). Ý nghĩa cần nắm:

- Không thực hiện operation cho target khi state chưa đủ an toàn.
- Bảo vệ ranh giới giữa helper xác nhận safe state và B tiếp tục.
- Không để self và helper đồng thời xử lý **cùng operation** ngoài hợp đồng.
- Hoàn tất/cancel operation khi target kết thúc đúng quy tắc quản lý vòng đời.
- Thông báo cho phía requester biết các conditions hoàn tất của operation đồng bộ.

Số tên lớp nội bộ như `HandshakeState` hoặc chi tiết `Semaphore`/`Mutex` của một commit HotSpot **không phải API public hay tài liệu thiết kế bất biến**. Hãy dựa trên invariants, đối chiếu source tương ứng với JDK version nếu cần debug sâu.

## 17. Handshake và Java Memory Model không thay thế nhau

Một sai lầm nguy hiểm:

> “Có handshake thì mình có thể đọc field thường của thread khác an toàn mà không cần volatile hoặc lock.”

**Sai.** Safepoint-safe liên quan sự ổn định và khả năng quan sát của JVM trong một callback nội bộ. Điều đó **không tự tạo quy tắc đồng bộ ứng dụng** cho mọi dữ liệu chia sẻ.

Trong chương trình minh họa:

```java
var running = new AtomicBoolean(true);
var counter = new AtomicLong();
```

Dùng `AtomicBoolean` để luồng khác nhìn thấy yêu cầu dừng theo hợp đồng concurrency, và `AtomicLong` để phép tăng/đọc bộ đếm được xử lý atomic. `CountDownLatch` dùng để phối hợp điểm bắt đầu/kết thúc; `Thread.join` bảo đảm chờ luồng kết thúc.

Nếu thay tất cả bằng trường `boolean` thường và vòng lặp tối ưu hóa cao, code có thể mắc lỗi visibility độc lập với việc JVM hỗ trợ thread-local handshakes.

### `volatile` có ý nghĩa riêng

`volatile` tạo các quan hệ visibility/happens-before cho việc đọc/ghi theo Java Memory Model. Nó không yêu cầu JVM dừng luồng đích tại safepoint hoặc chờ callback nội bộ.

**Tách hai tầng:**

| Tầng | Ví dụ | Mục tiêu |
| --- | --- | --- |
| **Java application concurrency** | `volatile`, `AtomicBoolean`, `synchronized`, `CountDownLatch` | Đồng bộ/visibility dữ liệu ứng dụng |
| **HotSpot safepoint/handshake** | Per-thread poll, safe-state checks, handshake closure | Cho VM thực hiện thao tác nội bộ với trạng thái luồng an toàn |

Không coi handshakes là cách làm thay hoặc tối ưu đồng bộ dữ liệu ứng dụng.

## 18. Bị chặn, native và những giới hạn về thời gian

Handshake không có cam kết real-time. Thời gian hoàn tất có thể thay đổi bởi:

- Scheduler chưa chạy target.
- Target đang trong một đoạn native/JNI/critical code.
- Target đang ở state transition cần được kiểm tra.
- Compiler/runtime đang thực hiện các công việc khác.
- Contention khi nhiều thread cùng xử lý một request nội bộ.
- Một số thao tác yêu cầu global safepoint thực sự.
- Cấu hình CPU/container và hoạt động GC.

Một luồng rất bận rộn **không nhất thiết** gây handshake chậm nếu liên tục đi qua safepoint polls; ngược lại một luồng chờ dài có thể được helper xử lý khi safe. Không thể đơn giản kết luận “bận thì không thể handshaking” hay “chờ thì luôn tức thì”.

### Còn native/JNI thì sao?

Trong một số trạng thái native, VM có thể xác nhận Java stack anchor có thể walk và thực hiện callback khi không phải chờ target chạy trở lại. Nhưng không phải mọi native call đều safe theo cùng cách. Khi trở lại Java, VM kiểm tra pending operations ở những transition cần thiết.

Các quy tắc dành cho native pinning và JVMTI cũng thay đổi theo JDK. Khi điều tra một runtime cụ thể, cần đọc logs và source **đúng JDK build**, không áp dụng một sơ đồ JDK 10 cho mọi chi tiết JDK 26.

## 19. JavaThread nội bộ khác `java.lang.Thread` và virtual thread

Đọc JEP 312 hoặc source HotSpot, bạn sẽ thấy từ **`JavaThread`**. Đây là lớp C++ bên trong HotSpot đại diện cho luồng thực thi Java trong VM. Nó không phải cùng type với `java.lang.Thread` của Java source.

Với **platform thread** truyền thống, việc lấy stack trace trong bài lab gắn với một luồng thực thi do HotSpot quản lý. Từ Java 21, **virtual threads** xuất hiện như một loại `java.lang.Thread`, có thể được mount/unmount trên carrier platform threads. Vì vậy không được mặc định:

- Mọi `java.lang.Thread` hiện đại ánh xạ **1:1 vĩnh viễn** tới một HotSpot `JavaThread`/OS thread.
- Handshake luôn nhắm trực tiếp từng virtual thread như một OS thread riêng.
- Chiến lược stack walking/continuation/carrier của virtual thread giống hệt ví dụ platform thread.
- Mọi lời gọi `getStackTrace()` của virtual thread sẽ tạo cùng `GetStackTraceClosure` log.

Bài lab chủ động dùng **platform threads** qua `new Thread(...)` để minh họa rõ hạ tầng JEP 312. Với virtual threads, hãy theo tài liệu và triển khai của phiên bản JDK đang sử dụng.

### Handshake không phải lệnh Thread.stop

`Thread.stop()` đã bị deprecated và loại bỏ khả năng tương thích theo thời gian vì nguy cơ làm hỏng bất biến ứng dụng. Cơ chế handshake an toàn của JVM **không trao quyền cho Java developer dừng cưỡng bức một luồng tùy ý giữa các instruction**. Để dừng công việc, dùng cooperative cancellation thông qua interrupt/flag/structured concurrency phù hợp.

## 20. Ứng dụng và hướng phát triển của cơ chế

Thread-local handshakes được thiết kế làm **hạ tầng VM đa mục đích**:

- Quan sát stack của một JavaThread với phạm vi mục tiêu hẹp.
- Hỗ trợ những nhu cầu diagnostics/profiling có lợi khi không phải dừng toàn JVM.
- Cung cấp cơ chế nhận các VM callbacks ở safe states.
- Là nền tảng cho những cải thiện JVM khác về latency và phối hợp thread.

Không cần khẳng định mọi tính năng JVMTI, JFR, profiler hay GC đều **chỉ** sử dụng handshake. Một số hoạt động vẫn cần global safepoint hoặc có cơ chế bất đồng bộ riêng.

### Tránh ví dụ chỉ đúng lịch sử

JEP 312 từng nêu **biased-lock revocation** như một trường hợp hứa hẹn tối ưu, nhưng **biased locking đã bị vô hiệu hóa/loại bỏ** trong quá trình phát triển Java sau đó. Vì Special Note chỉ lấy kiến thức còn áp dụng, bài tập trung vào **mô hình per-thread safepoint-safe callback và diagnostics vẫn tồn tại**, không hướng dẫn bật biased-locking flags hoặc coi cơ chế ấy là tính năng mặc định JDK hiện đại.

## 21. Đo lường và chẩn đoán handshake latency

Khi một hệ thống có nhiều thread hoặc cần quan sát phản hồi JVM, cần phân biệt:

- **Global safepoint pause**: ứng dụng có thể bị dừng trên phạm vi nhiều Java threads.
- **Handshake completion time**: thời gian một handshake request hoàn tất, không đồng nghĩa toàn ứng dụng bị STW với cùng duration.
- **Java application latency**: thời gian request người dùng, bao gồm scheduler, lock, I/O, GC và nhiều yếu tố khác.

Một log:

```text
Handshake "GetStackTraceClosure", Targeted threads: 1,
Executed by requesting thread: 0,
Total completion time: 27000 ns
```

không chứng minh tất cả luồng Java cùng bị ngưng trong 27 microseconds. Nó đo **thời gian hoàn tất operation đó** trên runtime/lần chạy tương ứng.

### Quy trình khi thấy handshake chậm

1. Xác định phiên bản JDK và runtime là HotSpot hay implementation khác.
2. Bật logging có kiểm soát: `-Xlog:handshake=info` trước, `trace` khi cần chi tiết.
3. Xem handshake type/closure name và số target.
4. Phân biệt self execution và requesting/helper processing nếu có log tương ứng.
5. Đối chiếu `-Xlog:safepoint=info` khi cần xem các global safepoints khác.
6. Kiểm GC pauses, native/JNI, thread dumps, CPU contention và thread states.
7. Quan sát nhiều lần, không kết luận từ một latency sample.
8. Nếu cần benchmark, chạy trên đúng JDK build, CPU/container limits, cùng workload.
9. Gỡ hoặc giảm verbose logging sau chẩn đoán để tránh overhead/để lộ thông tin runtime.

**Không nên** tăng/giảm random JVM internal flags của thread handshakes để “cắt giảm” latency trước khi có hiểu biết và tài liệu hỗ trợ. Nhiều flag từ JDK 10 không còn tồn tại hoặc không còn dành cho cấu hình production.

## 22. Những sai lầm phổ biến

### Lỗi 1 — Handshake phải dừng toàn JVM

Không. Mục tiêu của JEP 312 là cho phép **per-thread** callbacks không bắt buộc global safepoint. Một tác vụ toàn cục khác vẫn có thể dừng JVM độc lập.

### Lỗi 2 — Handshake là một callback Java do ứng dụng đăng ký

Không. Đây là **HotSpot internal mechanism**; không có public `Thread.handshake(Runnable)` trong Java SE.

### Lỗi 3 — Target nhất thiết phải tự thực thi callback

Không. Khi target ở safe blocked state, một handshaker/helper có thể thực hiện thay. Trên JDK 24 lab, log ghi requester xử lý thay blocked target.

### Lỗi 4 — Một thread khác cứ nhìn thấy `WAITING` là được sửa stack

Sai. `Thread.State` chỉ là trạng thái Java được quan sát; HotSpot cần kiểm tra/synchronization nội bộ để bảo đảm safe state ổn định.

### Lỗi 5 — `Thread.sleep` là một safepoint-poll API

Sai. Nó là API chờ theo thời gian. Polls thuộc interpreter/JIT/VM.

### Lỗi 6 — `Thread.yield` và `onSpinWait` chắc chắn khiến handshake hoàn tất

Sai. Đây là scheduler/spin hints. Không thể cam kết completion timing từ những lời gọi này.

### Lỗi 7 — Log `Executed by requesting thread: 1` là thread ID bằng 1

Sai. Đây là **số operation** mà requester thực hiện trong event tương ứng.

### Lỗi 8 — `getStackTrace()` luôn bắt buộc dùng GetStackTraceClosure

Sai. Java API không cố định implementation; kết quả lab đúng với HotSpot JDK 24. Runtime khác có thể dùng kỹ thuật khác.

### Lỗi 9 — Handshake đảm bảo data race của ứng dụng được sửa

Sai. Phải dùng `Atomic*`, `volatile`, locks, latch và Java Memory Model đúng cách.

### Lỗi 10 — Native thread luôn ở trạng thái an toàn

Sai. Phụ thuộc JNI/native state, khả năng đi dọc Java stack và transitions.

### Lỗi 11 — Mọi virtual thread tương đương một JavaThread/OS thread riêng

Sai. Virtual threads có thể sử dụng carrier platform threads và continuations; áp dụng assumptions 1:1 dễ dẫn tới giải thích sai.

### Lỗi 12 — Nhờ handshake nên mọi JVM operation từ Java 10 đều không STW

Sai. Global safepoints còn cần cho nhiều công việc khác. Handshake chỉ **mở thêm khả năng** thực hiện tác vụ có mục tiêu hẹp.

### Lỗi 13 — Đo completion time rồi gọi là “pause toàn ứng dụng”

Không đúng. Scope một handshake có thể chỉ là một target; app latency có nhiều thành phần khác.

### Lỗi 14 — Muốn test handshake thì gọi `Thread.stop()`

Sai và nguy hiểm. `Thread.stop` không phải cơ chế handshake và đã bị deprecated/loại bỏ. Dùng cooperative lifecycle.

### Lỗi 15 — Đưa tên class nội bộ của JDK 10 vào mã Java production

Không nên. Các lớp C++ nội bộ như `HandshakeState` là implementation details có thể đổi; use public, supported APIs trong code sản phẩm.

## 23. Checklist khi đọc source hoặc log HotSpot

1. **Đúng JDK release/build chưa?** Không áp dụng trực tiếp chi tiết một patch JDK 10 cho JDK 26.
2. **Đang xem global safepoint hay thread-local handshake?**
3. **Operation nhắm một target hay nhiều targets?**
4. **Target đang chạy Java, blocked, native hay transition?**
5. **Có bằng chứng poll được arm/target tự process không?**
6. **Có bằng chứng requester/helper process thay target không?**
7. **Có bảo vệ việc callback chỉ được xử lý theo hợp đồng không?**
8. **Có khả năng target kết thúc trong khi request đang pending không?**
9. **Kết quả timing là handshake completion hay stop-the-world pause?**
10. **Có log `handshake`, `safepoint` và GC cần đối chiếu không?**
11. **Có dùng `Thread.State` như dữ liệu tham khảo thay vì internal proof không?**
12. **Có phân biệt `Thread.onSpinWait` với safepoint poll không?**
13. **Có dùng `AtomicBoolean` hoặc visibility hợp lệ cho cờ điều khiển ứng dụng không?**
14. **Có dùng public supported API thay vì `jdk.internal.*` trong Java source không?**
15. **Có kiểm lý do JNI/native code trì hoãn execution không?**
16. **Có đang phân tích platform thread hay virtual thread?**
17. **Có tránh khai báo hiệu quả realtime/latency tuyệt đối không?**
18. **Có tránh assume mọi stack trace sẽ log cùng một closure name không?**
19. **Có đọc chính xác log number “Executed by requesting thread” không?**
20. **Có làm giảm verbose logging sau khi kết thúc điều tra không?**

## 24. Bài tập vận dụng

**Câu 1.** Mục tiêu của JEP 312 là dừng cả JVM ở global safepoint để xử lý một thread hay cho phép per-thread handshake?

**Câu 2.** Safepoint-safe state có đồng nghĩa với `Thread.State.WAITING` không?

**Câu 3.** Một thread chạy mã JIT làm sao biết VM có pending handshake theo nguyên lý tổng quát?

**Câu 4.** Có phải mọi Java statement là một safepoint poll không?

**Câu 5.** Nếu target đang chạy và gặp poll, ai có thể thực hiện callback?

**Câu 6.** Nếu target đang blocked trong một state được VM xác minh an toàn, ai có thể xử lý callback?

**Câu 7.** Vì sao VM phải đồng bộ khi target tự phục vụ và helper có thể xử lý thay?

**Câu 8.** `Thread.onSpinWait()` có buộc HotSpot thực thi pending handshake ngay lập tức không?

**Câu 9.** `Thread.interrupt()` có phải lời gọi `HandshakeClosure` của JEP 312 không?

**Câu 10.** Trong log `Targeted threads: 1, Executed by requesting thread: 1`, số 1 thứ hai có phải thread ID không?

**Câu 11.** Có thể xem `Thread.getStackTrace()` như API quản lý thread-local handshakes chính thức không?

**Câu 12.** Một callback trong handshake có bảo đảm transaction/data structures của ứng dụng đồng thời nhất quán không?

**Câu 13.** Nếu một target không được CPU scheduler chạy trong thời gian dài, handshake có cam kết completion deadline cố định không?

**Câu 14.** Java 21+ virtual threads có luôn ánh xạ 1:1 đến một OS thread cho toàn thời gian sống không?

**Câu 15.** Nếu hệ thống vẫn có global STW GC, điều đó chứng minh JEP 312 không hoạt động không?

**Câu 16.** Tại sao câu “đang ở native code luôn safe” là kết luận thiếu điều kiện?

**Câu 17.** Nên dùng gì để ứng dụng tự phối hợp dừng thread một cách chuẩn?

**Câu 18.** Trong lab, tại sao có thể có log `by self` khi target running và `by handshaker` khi target WAITING?

**Câu 19.** Có nên dùng legacy biased locking flag để thử nghiệm lợi ích handshakes trên JDK 26 không?

**Câu 20.** Vì sao không được lấy số nanoseconds của một handshake rồi tuyên bố đó là downtime toàn hệ thống?

**Đáp án:**

1. Cho phép per-thread handshakes mà **không bắt buộc global safepoint**.
2. Không; đây là một khái niệm VM internal và cần xác nhận điều kiện phù hợp.
3. Qua **safepoint polling** do VM/compiler/runtime bố trí.
4. Không; vị trí poll phụ thuộc compiler/interpreter và runtime.
5. Chính target trong đường `process-by-self`.
6. Một VM/helper/requesting thread thích hợp có thể xử lý thay theo quy tắc đồng bộ.
7. Để giữ safety invariant, không xử lý trùng callback hoặc thao tác trong lúc target đã tiếp tục chạy.
8. Không; `onSpinWait` chỉ là spin hint.
9. Không; `interrupt` có ngữ nghĩa cancellation/blocking riêng.
10. Không; đó là **số operation** trong log.
11. Không; API lấy stack trace không cam kết cách hiện thực.
12. Không; vẫn cần cơ chế Java Memory Model/locks phù hợp.
13. Không; scheduling/native/VM state ảnh hưởng latency.
14. Không; virtual threads dùng carriers và có thể mount/unmount.
15. Không; global safepoints vẫn cần cho những tác vụ khác.
16. Chỉ safe khi VM có thể xác nhận thread state/stack anchor và điều kiện không bị race.
17. `interrupt`, `AtomicBoolean`/`volatile`, `CountDownLatch`, cancellation hoặc cơ chế lifecycle được hỗ trợ.
18. Running thread có thể đến poll và tự process; blocked thread có thể được requester xử lý khi safe.
19. Không; biased locking là cơ chế lịch sử không còn mặc định/phù hợp ở JVM hiện đại.
20. Vì handshake có scope hẹp; completion time không đồng nhất với stop-the-world pause của tất cả application threads.

## 25. Tổng kết và nguồn còn áp dụng

- **JEP 312 (Java 10)** cung cấp hạ tầng **Thread-Local Handshakes** để thực hiện một VM callback ở thread target **không nhất thiết phải dừng tất cả Java threads**.
- An toàn dựa vào **safepoint-safe state**, không phải bất kỳ thời điểm nào trên luồng.
- Target đang chạy Java có thể tự phục vụ operation tại **safepoint poll**.
- Target đang blocked hoặc ở trạng thái khác đủ an toàn có thể được **helper/requester/VM xử lý thay** sau khi xác minh state ổn định.
- JVM phải bảo vệ race giữa **self processing** và **helper processing**, cũng như xử lý completion/lifecycle.
- `Thread.sleep`, `yield`, `onSpinWait` và `interrupt` **không** phải public handshake API.
- `Thread.getStackTrace` có thể giúp quan sát handshake logs trên HotSpot JDK 24, nhưng **không bảo đảm** implementation giống nhau ở mọi JDK.
- Handshake không thay thế `volatile`/`Atomic*`/locks của ứng dụng và không bảo đảm thời gian hoàn thành cố định.
- Với virtual threads và JDK mới, phân biệt `JavaThread` nội bộ với `java.lang.Thread`; không dùng assumptions 1:1 cho carrier threads.
- Chỉ sử dụng nguồn và APIs **còn áp dụng trong Java hiện đại**, tránh dùng legacy biased-locking examples/flags làm cách triển khai.

**Nguồn tham khảo:**

1. [OpenJDK JEP 312 — Thread-Local Handshakes](https://openjdk.org/jeps/312): động cơ và phạm vi per-thread callbacks không cần global safepoint.
2. [OpenJDK JDK 10 release features](https://openjdk.org/projects/jdk/10/): JEP 312 là tính năng Java 10.
3. [OpenJDK HotSpot — handshake.hpp, mã hiện hành](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/handshake.hpp): giao thức handshake và điều kiện an toàn theo runtime.
4. [OpenJDK HotSpot — handshake.cpp, mã hiện hành](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/handshake.cpp): self/helper paths và đồng bộ callback, chỉ để đọc hiểu implementation.
5. [OpenJDK HotSpot — safepointMechanism.hpp](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/safepointMechanism.hpp): safepoint polling và per-thread poll control.
6. [Java SE 26 — Thread.getStackTrace](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.html#getStackTrace()): public API stack trace, không cam kết chiến lược handshake bên dưới.
7. [Java SE 26 — Thread.onSpinWait](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.html#onSpinWait()): spin-loop hint, không phải handshake request.
8. [Java SE 26 — AtomicBoolean](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/AtomicBoolean.html): visibility và atomic state cho phối hợp ứng dụng.
9. [Java SE 26 — The java Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): Unified Logging `-Xlog` và cách xem hỗ trợ logging.
10. [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): phân biệt virtual threads với platform/carrier threads.
