# Thao tác phối hợp hướng đến một luồng hoặc một tập luồng — Thread-Local Handshakes

*Chủ đề cha: Handshake theo luồng. Bài Knowledge thuộc Java 10, tập trung vào ý nghĩa và cách JVM HotSpot phối hợp một thao tác an toàn **với một luồng mục tiêu hoặc với nhiều luồng được chọn**, thay vì buộc mọi luồng Java cùng dừng tại một global safepoint. Cơ chế được đưa vào qua JEP 312 trong JDK 10 và tiếp tục có vai trò trong HotSpot hiện đại. Đây là **cơ chế nội bộ của JVM**, không phải một public Java SE API có tên `Thread.handshake()`. Các chương trình Java 17+/21+ dưới đây là minh họa và công cụ quan sát, không giả vờ trực tiếp thực thi closure nội bộ của HotSpot.*

## 1. Bắt đầu bằng một tình huống

Giả sử một tiến trình có ba luồng nền tảng (platform threads):

- Luồng **A** thực hiện công việc A.
- Luồng **B** thực hiện công việc B.
- Luồng **C** thực hiện công việc C.

Một tác vụ nội bộ của JVM chỉ cần xử lý trạng thái an toàn của **B**. Nếu buộc A, B, C cùng đến một điểm dừng toàn cục chỉ để nhìn vào B, JVM có thể phải trả thêm chi phí phối hợp không cần thiết.

Thread-local handshake cho JVM khả năng yêu cầu **B** tham gia một thao tác trong trạng thái an toàn, trong khi **A và C không bắt buộc phải tạm dừng bởi chính thao tác này**. Khi cần xử lý **A và C**, JVM có thể tổ chức các yêu cầu hướng đến các luồng liên quan, thay vì suy rằng cả ba luôn phải đi qua cùng một rào chắn toàn cục.

Sơ đồ khái niệm:

```text
  VM / subsystem muốn thực hiện operation H

       Trường hợp một mục tiêu: B
                 |
                 v
  A: tiếp tục --> [không bị nhắm]
  B: chạy -----> [handshake-safe] -> xử lý H(B) -> tiếp tục
  C: tiếp tục --> [không bị nhắm]

       Trường hợp tập mục tiêu: {A, C}
               /           \
              v             v
  A: chạy -> [safe] -> H(A) -> tiếp tục
  B: chạy -> [không có H(B), không bị ép vào barrier chung]
  C: chạy ------> [safe] -> H(C) -> tiếp tục

  Hai thời điểm hoàn thành H(A), H(C) có thể khác nhau.
```

**Ý then chốt:** xử lý một tập mục tiêu là tập hợp những lần phối hợp **theo luồng**, không đồng nghĩa tạo một “ảnh chụp atomic” tại đúng một thời điểm chung của toàn bộ tập. Một operation cần đồng bộ toàn cục vẫn có thể phải dùng safepoint toàn cục hoặc cơ chế khác phù hợp.

## 2. Mục tiêu của bài

Sau bài này, bạn có thể:

1. Giải thích JEP 312 bổ sung khả năng gì cho HotSpot kể từ Java 10.
2. Phân biệt handshake hướng đến **một JavaThread**, nhiều JavaThreads đã chọn và **tất cả JavaThreads**, với global safepoint.
3. Hiểu callback/closure nội bộ chỉ được xử lý trong **trạng thái thread-safe phù hợp**.
4. Biết callback có thể được xử lý bởi target hoặc một luồng JVM/handshaker thích hợp khi target an toàn, chứ không bảo đảm luôn chạy trên target.
5. Giải thích vì sao A, C có thể tiếp tục khi chỉ B là mục tiêu.
6. Biết group handshake không mặc định có một global stop-the-world barrier.
7. Nhận diện các rủi ro: target kết thúc, chậm đến handshake point, operation bị chặn, race và thứ tự hoàn thành.
8. Phân biệt **HotSpot internal handshake** với `Thread.interrupt()`, `Thread.join()`, `CountDownLatch`, `ThreadMXBean` và callback do ứng dụng tự thiết kế.
9. Viết ví dụ Java 17+ *mô phỏng định tuyến công việc đến đúng worker* mà không nói sai rằng nó gọi JEP 312.
10. Quan sát một tập thread bằng public management API trên Java 21+, đồng thời hiểu đó không phải public HotSpot handshake.
11. Dùng unified logging của HotSpot để hỗ trợ chẩn đoán mà không coi mọi dòng log hoặc tình trạng không có log là bằng chứng tuyệt đối.
12. Xác định giới hạn với virtual threads (Java 21+) và các bản JDK/vendor/runtime khác nhau.
13. Tránh dùng cờ JVM cũ/không ổn định hoặc Thread API không còn phù hợp để “ép” handshakes.

## 3. JEP 312: cơ sở kỹ thuật có từ Java 10

**JEP 312 — Thread-Local Handshakes** giới thiệu một cách để JVM yêu cầu xử lý callback trên từng Java thread **mà không nhất thiết phải tạo một global VM safepoint**. Trước cơ chế này, một số công việc cần một luồng Java đạt trạng thái an toàn lại phải dựa trên phối hợp dừng toàn JVM.

JEP 312 không tạo một class/thư viện mới trong `java.lang.Thread`. Nó đặt **nền tảng trong HotSpot** để các subsystem như quản lý runtime, garbage collector, tooling/JVMTI và những tối ưu cần kiểm tra thread state có cơ hội giảm phạm vi tạm dừng.

**Phân biệt mốc lịch sử với hành vi hiện tại:**

- **Java 10:** JEP 312 giới thiệu thread-local handshakes.
- **JDK mới hơn:** HotSpot tiếp tục điều chỉnh implementation, đóng gói operation, hỗ trợ đồng bộ/bất đồng bộ trong các tình huống nội bộ, và tích hợp thêm với tooling/runtime.
- **Java SE public API:** vẫn không có method chuẩn `Thread.handshake()` dành cho ứng dụng tự đăng một C++ handshake closure.
- **Cờ tùy chọn JVM lịch sử:** một số bài hướng dẫn Java 10 đề cập `-XX:ThreadLocalHandshakes`. Không dựa vào cờ cũ này cho JDK 17/21/25 vì các tùy chọn HotSpot có thể bị loại bỏ/thay đổi; hãy kiểm tra runtime thực tế thay vì copy lệnh legacy.

Mục tiêu của bài không phải sửa mã nguồn HotSpot. Người lập trình Java cần hiểu **vì sao một số thao tác chẩn đoán/thu thập thông tin luồng có thể được xử lý ít gây global pauses hơn**, đồng thời biết những giới hạn của cơ chế đó.

### 3.1. Các thuật ngữ

| Thuật ngữ | Ý nghĩa trong bài |
| --- | --- |
| **JavaThread** | Đối tượng native/runtime dùng trong HotSpot để đại diện một luồng thực thi Java phù hợp; không đồng nhất một-một với mọi `java.lang.Thread` trong thế giới virtual threads |
| **Target** | JavaThread hoặc thực thể phù hợp mà một handshake operation hướng đến |
| **Handshake closure / callback** | Thao tác nội bộ cần được thực hiện đối với thread mục tiêu khi trạng thái an toàn |
| **Thread-local poll** | Điểm/kiểm tra của HotSpot cho phép một thread nhận biết yêu cầu phối hợp dành cho nó |
| **Handshake-safe state** | Trạng thái mà operation có thể thực hiện với những bảo đảm nội bộ cần thiết |
| **Global safepoint** | Cơ chế phối hợp tất cả JavaThreads phù hợp tới trạng thái dừng/safe chung để thực hiện công việc yêu cầu toàn VM |
| **Handshake requester** | Phần JVM/tooling nội bộ yêu cầu operation |
| **Completion** | Operation cho target đã được xử lý hoặc đã có kết quả theo protocol tương ứng |
| **Subset** | Tập JavaThreads được chọn; không phải một Java Set mà application truyền vào public `Thread.handshake(Set)` |
| **STW** | Stop-the-world, dùng khi một công việc JVM thực sự cần ngừng mutator threads ở phạm vi thích hợp |

Cần hiểu các từ “đồng bộ” và “handshake” theo **VM-internal protocol**, không phải mặc định là synchronized block hoặc giao thức bắt tay TLS.

## 4. Một target: phối hợp với đúng luồng cần xử lý

Ví dụ VM cần đọc thông tin liên quan tới **B** theo một trạng thái nội bộ an toàn.

Một chuỗi logic cấp cao:

1. Requester xác định target `JavaThread B` còn hợp lệ.
2. VM/handshake infrastructure tạo một operation mang closure thích hợp.
3. Operation được gắn vào trạng thái/queue handshake của B.
4. B có cơ chế polling hoặc chuyển trạng thái để có thể xử lý operation khi an toàn.
5. Callback thực hiện đối với B ở **handshake-safe state**.
6. Completion được ghi nhận, resource/lifetime được xử lý theo protocol của JVM.
7. B tiếp tục hoạt động bình thường nếu operation không nhằm giữ B bị suspend.
8. A và C không bị bắt buộc dừng **chỉ vì yêu cầu nhắm vào B**.

Không phải callback nào cũng được thi hành bởi B. Theo mã nguồn HotSpot hiện đại, tùy **loại closure** và trạng thái mục tiêu, nó có thể được thực thi bởi target, initiating thread hoặc VMThread/handshaker trong khi target ở trạng thái blocked an toàn. Vì vậy **đừng diễn đạt “callback luôn chạy trên stack của B”**.

### 4.1. Khi B đang chạy Java code

Một JavaThread đang chạy có thể cần đi tới một **poll** hoặc điểm chuyển trạng thái thích hợp trước khi handshake được xử lý. Vì thế thao tác không có tính “ngay lập tức trong 0 ns”, và một vòng lặp phải được JVM bảo đảm các cơ chế polling theo implementation.

Người viết ứng dụng không cần tự chèn `Thread.yield()` hay `Thread.sleep()` chỉ để “bật JEP 312”. Những lời gọi này là public Java APIs có hợp đồng riêng; không phải API để chỉ huy handshake nội bộ.

### 4.2. Khi B đang blocked hoặc ở native/VM state

Một thread có thể đang chờ monitor, đang trong hệ điều hành, ở native call hoặc trạng thái không an toàn cho một operation nào đó. VM phải **kiểm tra điều kiện an toàn**, thay vì áp callback tùy ý vào mọi trạng thái.

Nếu một VM/handshaker có thể chứng minh target đang ở trạng thái phù hợp và giữ nó blocked đúng protocol, operation có thể được thực hiện **thay cho target**. Nếu chưa an toàn, operation chờ target đi tới trạng thái thích hợp hoặc chuyển theo quy trình của JVM.

**Không đồng nhất:** “B đang WAITING trong `Thread.State`” và “mọi handshake closure đều được phép chạy trên B”. `Thread.State` là mô hình API của Java, không phải mô hình an toàn đầy đủ của HotSpot.

### 4.3. Khi B sắp kết thúc

Từ lúc chọn target đến khi xử lý có thể có race: B kết thúc hoặc không còn thuộc thread list. Runtime phải bảo vệ vòng đời và xử lý cancellation/completion sao cho không truy cập con trỏ stale.

Trong HotSpot hiện đại, các cơ chế như `ThreadsListHandle` và lifecycle/protocol nội bộ hỗ trợ bảo vệ target. Đây **không phải** lời mời ứng dụng lấy địa chỉ native `JavaThread*` rồi tự giữ sau khi luồng kết thúc.

Không khẳng định handshake luôn thành công trên một target đã chết hoặc sẽ được áp lên “thread mới” có tên tương tự. **Identity và lifetime của target cần được xác định trong thời điểm request.**

## 5. Một tập target: A và C, không phải B

Bài học chính của mục này là phạm vi phối hợp có thể là **tập thread thực sự liên quan**. Giả sử VM cần thực hiện cùng một operation đối với A và C:

```text
Input logic: selectedTargets = { A, C }

  1. Xác định danh sách target còn sống và hợp lệ.
  2. Gửi/thiết lập các operation phù hợp cho A, C.
  3. A đạt state an toàn; xử lý operation của A.
  4. A có thể tiếp tục ngay sau khi hoàn thành phần của nó.
  5. C đạt state an toàn vào thời điểm khác; xử lý operation của C.
  6. Requester có thể tổng hợp trạng thái hoàn thành A và C.
  7. B không bị yêu cầu xử lý operation này.

Output: kết quả per-target, không tự tạo một snapshot atomic.
```

**Đây là sơ đồ khái niệm**, không phải Java code hay tên public HotSpot API nhận một `Set<Thread>`. Các bản HotSpot cung cấp những primitive nhắm một JavaThread, mọi JavaThreads và các protocol phối hợp nhiều target; không được tự giả định một overload Java SE `handshake(Collection<Thread>)` tồn tại.

### 5.1. Khi nào nên chọn một mục tiêu?

- Một VM service cần quan sát/truy vấn trạng thái **một** JavaThread.
- Một operation được thiết kế an toàn khi chỉ target phải đi tới safe state.
- Không có bất biến toàn cục đòi mọi thread dừng cùng thời điểm.
- Chi phí phối hợp toàn VM sẽ lớn hơn nhu cầu thực tế.

**Không phải cứ dữ liệu ở B là có thể làm mọi thứ bằng one-thread handshake.** Nếu logic thay đổi cấu trúc chung mà A/C vẫn đang truy cập hoặc cần snapshot nhất quán trên toàn heap, có thể phải dùng global coordination.

### 5.2. Khi nào nên chọn một tập mục tiêu?

- Dữ liệu cần xử lý chỉ liên quan tới những JavaThreads được chọn.
- Mỗi per-thread closure có thể chạy trong trạng thái an toàn của chính target.
- Requester có thể chấp nhận completion của từng target ở các thời điểm khác nhau.
- Các thread ngoài tập không cần tham gia barrier chung cho operation đó.

Ví dụ quan sát trạng thái của tập thread phục vụ một subsystem, hoặc làm một công việc theo từng stack/JavaThread. Đây là **kiểu bài toán**, không phải cam kết mọi diagnostic tool cụ thể dùng một API handshake giống nhau trên mọi JDK.

### 5.3. All-threads handshake vẫn khác global safepoint

Một VM có thể cần thực hiện cùng một per-thread operation cho **tất cả JavaThreads**, nhưng mỗi thread có thể đi đến handshake-safe state và hoàn thành operation theo thời điểm riêng. Nó **không tự biến thành** global safepoint nơi tất cả bị giữ ở một barrier tới khi VM-wide action xong.

```text
Thời gian --->
 A: ---[H(A)]-----running------------------>
 B: --------[H(B)]---running--------------->
 C: --[H(C)]---------running--------------->

 Tất cả nhận H; không bắt buộc A, B, C cùng đứng yên.
```

Ngược lại, **global safepoint** dùng khi cần những bảo đảm toàn VM: các thread liên quan được phối hợp vào trạng thái an toàn và giữ theo protocol của global operation. Hai cơ chế có mục đích và điều kiện an toàn khác nhau.

**Không suy rằng all-thread handshake == nhất quán tại một thời điểm trên mọi thread.** Nếu yêu cầu dữ liệu được chụp trong cùng một khoảng yên lặng toàn cục, phải thiết kế protocol đó chứ không suy ra từ số target.

## 6. So sánh các kiểu phối hợp

| Tiêu chí | Handshake một target | Handshake tập/đa target | Handshake trên mọi target | Global safepoint |
| --- | --- | --- | --- | --- |
| Phạm vi | Một JavaThread | Các JavaThreads được chọn | Mọi JavaThreads phù hợp | Phạm vi toàn VM được yêu cầu |
| Yêu cầu dừng luồng không liên quan | Không bởi chính operation đó | Không bởi chính operation đó | Không bắt buộc cùng dừng lâu | Các luồng liên quan được đồng bộ vào barrier |
| Thời điểm completion | Một target | Theo từng target | Theo từng target | Có giai đoạn dừng/tiếp tục đồng bộ |
| Snapshot toàn cục atomic | Không tự bảo đảm | Không tự bảo đảm | Không tự bảo đảm | Có thể phục vụ operation cần trạng thái toàn cục ổn định theo protocol |
| Chi phí | Phụ thuộc target/state | Phụ thuộc số target/chậm nhất và phối hợp | Phụ thuộc tập toàn bộ | Có chi phí gom các thread vào safepoint |
| Chủ thể điều khiển | HotSpot internal | HotSpot internal/subsystem | HotSpot internal | HotSpot internal |
| Public Java API để gọi trực tiếp | Không | Không | Không | Không |
| Ví dụ ý nghĩa | Truy vấn an toàn một thread | Thao tác cùng loại trên subset | Per-thread cleanup/inspection | Những công việc thực sự cần STW hoặc VM-wide consistency |

Bảng là khái niệm tổng quát, không mô tả một cam kết hiệu năng hoặc chi tiết triển khai bất biến mọi release. Một handshake có thể phải chờ thread lâu, và một global safepoint ngắn có thể hoàn thành rất nhanh. Hãy đo thay vì kết luận handshake **luôn** nhanh hơn.

## 7. Callback được thi hành bởi ai?

Đây là điểm kỹ thuật dễ hiểu sai. Một bản mô tả đơn giản thường nói “luồng tự chạy callback tại poll”, nhưng HotSpot hiện đại cho phép nhiều hình thức xử lý tùy closure.

Theo phần chú giải của `src/hotspot/share/runtime/handshake.hpp` trong OpenJDK:

- Handshake closure liên quan tới một JavaThread trong trạng thái safepoint/handshake-safe.
- Tùy bản chất closure, **initiating thread**, **target thread** hoặc **VMThread** có thể thực hiện.
- Nếu không phải target thực thi, target phải được giữ **blocked** trong lúc operation được làm thay cho nó.

Điều này đáp ứng cả trường hợp target đang chạy Java code và trường hợp target ở một trạng thái mà một handshaker khác có thể xử lý an toàn. Nó cũng phủ nhận giả định “callback luôn chạy bởi chính thread B”.

### 7.1. Protocol phải ngăn thực thi trùng

Nếu B và một VMThread cùng có khả năng xử lý một pending operation, runtime phải **bảo đảm không cả hai thực thi trùng cùng một synchronous closure**. HotSpot có cơ chế queue, lock/ownership và completion nội bộ để phân công quyền xử lý.

Đó là một lý do quan trọng vì sao **không nên tự mô phỏng VM handshakes bằng việc giữ một `Thread` Java object rồi tùy tiện chặn/resume nó**. Các cơ chế nội bộ bảo vệ những trạng thái mà Java API không biểu diễn đầy đủ.

### 7.2. Closure không tùy tiện như `Runnable`

Một closure được HotSpot gọi trong handshake-safe state phải tuân theo **hạn chế đặc biệt của VM code** về thread state, resource management, locks, safepoints, thread lifecycle và việc được phép chạy trên target hay thread khác. Nó không tương đương một `Runnable` bất kỳ được đặt vào Java Executor.

Các class C++ `Handshake`, `HandshakeClosure` và `HandshakeState` là **internal implementation details**, không phải thư viện Java SE. Signature có thể thay đổi khi HotSpot được bảo trì. Không đưa C++ fragment vào Java project rồi bảo nó có thể biên dịch bằng `javac`.

## 8. Mối liên hệ với safepoint polling

Thread-local handshakes dựa vào khả năng JVM biết khi một JavaThread đạt trạng thái an toàn để thực hiện operation.

Khái quát:

1. JVM yêu cầu operation và cập nhật trạng thái polling/queue cho target.
2. Khi target chạy tới một poll hoặc chuyển state, runtime kiểm tra pending work.
3. Nếu có operation phù hợp, target/handshaker xử lý nó theo safe-state protocol.
4. Operation được đánh dấu complete, target có thể tiếp tục.
5. Nếu có request khác, VM có thể tiếp tục xử lý theo cơ chế nội bộ.

### 8.1. Polling không phải lời hứa deadline

Cơ chế có thể làm một handshake hoàn thành nhanh, nhưng không có cam kết public Java SE rằng “sau 1 ms mọi target sẽ thực hiện xong”.

Lý do latency thay đổi:

- Thread có thể chưa đi qua điểm polling thích hợp.
- Thread có thể ở native code, kernel wait hoặc trạng thái không an toàn cho closure cụ thể.
- Operation có thể phải đợi lock/resource hoặc VM operation khác.
- Target có thể kết thúc, bị pause bởi subsystem khác hoặc cần quản lý race.
- Khi phối hợp nhiều target, thời gian toàn yêu cầu có thể phụ thuộc target chậm nhất.

**Không viết test assert tuyệt đối rằng một handshake sẽ luôn xong sau 2 ms trên mọi CPU/JDK.** Benchmark và log phải gắn với workload và runtime thật.

### 8.2. Không nhất thiết mọi thread đều “tự chạy” operation

Một thread ở blocked safe state có thể được hỗ trợ xử lý bởi VMThread/initiating thread. Vì vậy tài liệu nên nói *operation được thực hiện đối với target ở trạng thái an toàn* thay vì *target luôn tự gọi callback*.

### 8.3. Polling do JVM quản lý, không phải app tự chèn `yield`

`Thread.yield()` là gợi ý scheduler. `Thread.sleep()` là thao tác chờ; `Thread.onSpinWait()` là spin-wait hint. Chúng có mục đích riêng và **không phải public switches của JEP 312**. Java compiler/JIT/HotSpot chịu trách nhiệm đặt, kiểm tra hoặc thực hiện cơ chế poll theo implementation.

## 9. Đọc đúng ý “một luồng hoặc một tập luồng”

Đề bài có hai cấp phạm vi:

**A. Một luồng:** chọn đúng một target và một operation. Không ép thread khác tham gia nếu không cần.

**B. Tập luồng:** chọn nhiều target liên quan, xử lý operation theo từng luồng rồi tổng hợp kết quả/completion. Tập này có thể là hai, một nhóm hoặc all-threads tùy VM subsystem. Đừng coi “tập” đồng nghĩa một lời gọi C++ API chung bảo đảm các target cùng dừng và callback cùng chạy tại một khoảnh khắc.

Sơ đồ tiến độ:

```text
       Dispatcher VM/subsystem
                 |
       +---------+--------+
       |                  |
   target A            target C
       |                  |
  A reaches safe     C not safe yet
       |                  |
  H(A) completes     waits/handshaker checks state
       |                  |
  A resumes          C reaches safe
                          |
                      H(C) completes
                          |
                      C resumes

  Requested set {A,C} complete after both have completed.
  B is not among requested targets.
```

Không cần giả định H(A), H(C) dùng chung một callback object C++ theo cách share mutable state thiếu đồng bộ; VM subsystem phải thiết kế ownership, kết quả và serialization thích hợp. Nếu một target không còn alive, completion/cancellation phải phản ánh trường hợp đó theo API nội bộ đang sử dụng.

## 10. Chương trình Java 17 minh họa ý tưởng chọn target

**Quan trọng:** chương trình dưới đây **không gọi internal HotSpot handshake**. Nó là một mô hình học tập ở tầng Java, dùng **mailbox** và **`BlockingQueue`** để cho thấy một yêu cầu có thể hướng tới một worker hoặc subset worker. Trong thực tế, VM handshakes dùng polling và safepoint-safe protocol của HotSpot, không phải mailbox Java như ví dụ.

Tạo file **`CooperativeTargetsDemo.java`**:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicInteger;

public final class CooperativeTargetsDemo {
    private static final Runnable STOP = () -> {};

    static final class Worker {
        private final BlockingQueue<Runnable> mailbox =
                new LinkedBlockingQueue<>();
        private final AtomicInteger processed = new AtomicInteger();
        private final Thread thread;

        Worker(String name) {
            thread = new Thread(() -> {
                try {
                    while (true) {
                        Runnable task = mailbox.take();
                        if (task == STOP) {
                            return;
                        }
                        task.run();
                    }
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            }, name);
            thread.start();
        }

        CompletableFuture<String> request() {
            var reply = new CompletableFuture<String>();
            mailbox.add(() -> {
                processed.incrementAndGet();
                reply.complete(Thread.currentThread().getName());
            });
            return reply;
        }

        int count() {
            return processed.get();
        }

        void stop() throws InterruptedException {
            mailbox.add(STOP);
            thread.join();
        }
    }

    public static void main(String[] args) throws Exception {
        Worker a = new Worker("A");
        Worker b = new Worker("B");
        Worker c = new Worker("C");

        try {
            // Một mục tiêu: B. A/C không nhận nhiệm vụ này.
            System.out.println("single=" + b.request().join());
            System.out.println("afterSingle="
                    + a.count() + "," + b.count() + "," + c.count());

            // Tập hai mục tiêu: A và C, không gửi đến B.
            var ra = a.request();
            var rc = c.request();

            System.out.println("subset=["
                    + ra.join() + ", " + rc.join() + "]");
            System.out.println("afterSubset="
                    + a.count() + "," + b.count() + "," + c.count());
        } finally {
            a.stop();
            b.stop();
            c.stop();
        }
    }
}
```

Biên dịch/chạy bằng Java 17 trở lên:

```bash
javac --release 17 CooperativeTargetsDemo.java
java CooperativeTargetsDemo
```

Stdout đã kiểm thử:

```text
single=B
afterSingle=0,1,0
subset=[A, C]
afterSubset=1,1,1
```

### 10.1. Phân tích output

- `single=B`: chỉ B được gửi yêu cầu đầu tiên, B nhận request và trả tên chính mình.
- `afterSingle=0,1,0`: A/C chưa xử lý request nào của chương trình; chỉ bộ đếm B tăng.
- `subset=[A, C]`: gửi request cho A và C, sau đó lấy kết quả theo thứ tự đã định trong main, không phụ thuộc thứ tự hai worker xử lý thật.
- `afterSubset=1,1,1`: A và C mỗi thread xử lý một nhiệm vụ; B vẫn giữ count 1, không bị yêu cầu mới khi xử lý subset.
- `CompletableFuture.join()` ở đây đợi kết quả **của request Java**, không chứng minh một VM handshake đã chạy.
- `STOP` giúp đóng worker sạch sẽ khi demo kết thúc; không dùng các phương thức dừng luồng cưỡng ép đã lỗi thời.

Cách in được xây để deterministic: main chỉ kiểm tra bộ đếm sau khi các `CompletableFuture` đã hoàn thành. Mặc dù A và C có thể xử lý theo thứ tự bất kỳ, chuỗi in vẫn đưa A trước C do main ghép kết quả theo thứ tự `ra` rồi `rc`.

### 10.2. Vì sao ví dụ này chỉ là mô phỏng?

Khác biệt chủ yếu:

| Mailbox Java của ví dụ | Thread-local handshake của HotSpot |
| --- | --- |
| Ứng dụng tạo `Runnable` và Queue | HotSpot tạo internal handshake closure/protocol |
| Target tự lấy nhiệm vụ bằng `mailbox.take()` | Target hoặc VM/handshaker thực hiện tại trạng thái handshake-safe |
| Không quản lý native JavaThread state | Có kiểm tra state/lifecycle/serialization nội bộ |
| Dùng `CompletableFuture` đợi kết quả | VM dùng completion/protocol nội bộ |
| Chỉ xử lý công việc hợp đồng ứng dụng | Có thể thao tác metadata/stack/runtime state phù hợp |
| Không có quyền truy cập cấu trúc VM | Là cơ chế được sử dụng bên trong JVM |

**Mục đích giáo dục:** người học thấy vì sao việc nhắm một target hay subset tránh việc gửi yêu cầu tới thread không liên quan. Không được lấy việc demo chạy thành công làm bằng chứng JEP 312 được gọi ở bước `mailbox.add(...)`.

## 11. Truy vấn một tập luồng qua public management API (Java 21+)

Nếu muốn **quan sát một subset thread thật** từ code Java có chuẩn API, `java.lang.management.ThreadMXBean` cho phép truy vấn thông tin theo thread IDs. Việc API này chọn đúng IDs không có nghĩa một application có thể trực tiếp điều khiển HotSpot handshake; implementation của công cụ chẩn đoán có thể thay đổi theo JDK.

Ví dụ sử dụng `Thread.threadId()` (API từ Java 19) và biên dịch cho **Java 21+** để tránh `Thread.getId()` đã deprecated. Nó không phải chương trình Java 17; ví dụ Java 17 ở mục trước vẫn là chương trình nền tảng.

Tạo file **`SelectedThreadInfoDemo.java`**:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.util.Arrays;
import java.util.concurrent.CountDownLatch;

public final class SelectedThreadInfoDemo {
    private static void awaitRelease(
            CountDownLatch started, CountDownLatch release) {
        started.countDown();
        try {
            release.await();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    public static void main(String[] args) throws Exception {
        var started = new CountDownLatch(3);
        var release = new CountDownLatch(1);

        var a = new Thread(
                () -> awaitRelease(started, release), "worker-A");
        var b = new Thread(
                () -> awaitRelease(started, release), "worker-B");
        var c = new Thread(
                () -> awaitRelease(started, release), "worker-C");

        a.start();
        b.start();
        c.start();

        try {
            started.await();

            // Chỉ yêu cầu thông tin A và C; không đưa B vào danh sách.
            long[] targets = {a.threadId(), c.threadId()};

            ThreadInfo[] info =
                    ManagementFactory.getThreadMXBean()
                            .getThreadInfo(targets, 0);

            System.out.println("requested=" + targets.length);
            System.out.println("selected="
                    + Arrays.toString(Arrays.stream(info)
                    .map(ThreadInfo::getThreadName)
                    .toArray(String[]::new)));
            System.out.println("excludedB="
                    + Arrays.stream(info).noneMatch(
                    t -> t.getThreadName().equals("worker-B")));
            System.out.println("allAlive="
                    + (a.isAlive() && b.isAlive() && c.isAlive()));
        } finally {
            release.countDown();
            a.join();
            b.join();
            c.join();
        }
    }
}
```

Biên dịch/chạy với JDK 21 trở lên:

```bash
javac --release 21 SelectedThreadInfoDemo.java
java SelectedThreadInfoDemo
```

Stdout đã kiểm thử trên JDK hiện đại:

```text
requested=2
selected=[worker-A, worker-C]
excludedB=true
allAlive=true
```

### 11.1. Giải thích tính xác định

- Ba worker đều báo `started` và sau đó chờ `release`.
- Vì chưa mở `release`, chúng vẫn alive khi main lấy thông tin.
- `targets` chỉ chứa IDs của A và C, theo đúng thứ tự tạo mảng.
- `ThreadMXBean.getThreadInfo(targets, 0)` yêu cầu thông tin với độ sâu stack tối đa bằng 0 và trả kết quả tương ứng theo thứ tự IDs.
- `excludedB=true` xác nhận kết quả không có thread B.
- `finally` mở latch rồi `join` để không bỏ lại thread đang chờ.

Từ đó thấy **public API cũng có các thao tác quan sát một tập thread được chọn**, nhưng **không có hợp đồng Java SE bảo đảm call này luôn dùng JEP 312, luôn không gây safepoint, hoặc có cùng chi phí trên mọi VM**. Không lấy nó làm benchmark trực tiếp của handshake nội bộ.

### 11.2. Cách nghĩ đúng khi debug production

Nếu debugger/JFR/profiler/JVMTI agent yêu cầu thông tin một target/subset, implementation có thể dùng nhiều primitive VM khác nhau. Trên HotSpot hiện đại, handshakes là **một cơ sở quan trọng** cho những công việc có thể thực hiện per-thread.

Hãy kiểm tra tài liệu/cấu hình của chính công cụ, thay vì tuyên bố tất cả lần gọi `ThreadMXBean` đều phải dùng thread-local handshake.

## 12. Cái gì KHÔNG phải một HotSpot handshake?

Những API thường bị nhầm:

### 12.1. `Thread.join()`

`join()` đợi **một thread kết thúc**. Nó không yêu cầu HotSpot chạy một closure an toàn trên target.

```java
Thread worker = new Thread(() -> System.out.println("done"));
worker.start();
worker.join();
```

Đoạn trên cần nằm trong method xử lý `InterruptedException`; nó minh họa lifecycle của một thread. `join` không phải một request để đọc stack/VM metadata của thread đó tại một handshake-safe state.

### 12.2. `Thread.interrupt()`

`interrupt()` gửi tín hiệu ngắt theo quy tắc Java. Nó có thể làm một số blocking operation ném `InterruptedException` hoặc đặt interrupted status. Đây không phải “cơ chế nội bộ JEP 312” để thực thi callback an toàn đối với thread target.

Không thể suy `Thread.interrupt()` sẽ ngay lập tức kết thúc mọi CPU-bound task. Ứng dụng cần kiểm tra/interact với interrupted status và quản lý cancellation đúng hợp đồng.

### 12.3. `CountDownLatch` / `CyclicBarrier` / `Phaser`

Đây là các **public coordination utilities** giữa thread của ứng dụng. Chúng thích hợp khi bạn **cố ý** tạo đồng bộ ở tầng business code. Chúng không cho phép ứng dụng can thiệp vào safepoint-safe native state của JVM.

**Ví dụ quan trọng:** `CyclicBarrier` làm các participant đợi nhau theo một barrier tại code Java. Một tập HotSpot handshakes **không tự có** barrier tất cả participant như vậy. Chỉ khi VM subsystem thiết kế một global/collective protocol mới có những bảo đảm chung tương ứng.

### 12.4. `ThreadLocal<T>`

`ThreadLocal` cho phép lưu giá trị riêng theo thread của ứng dụng. Tên chứa chữ “thread-local” nhưng nó **không phải** `Thread-Local Handshakes`. Đặt một `ThreadLocal` không tạo safepoint, không chọn nhóm target, và không làm VM callback.

### 12.5. `synchronized` / `Lock`

Các primitives Java để bảo vệ dữ liệu chia sẻ, không đồng nhất với handshake tại safepoint-safe state. Việc JVM triển khai chúng có thể tương tác với runtime ở mức thấp, nhưng user code không kiểm soát một VM handshake thông qua việc khóa monitor.

### 12.6. TLS handshake

“Handshake” trong TLS/JSSE là việc hai điểm cuối mạng xác thực và thương lượng bảo mật. Nó hoàn toàn khác `JEP 312`, dù có cùng từ tiếng Anh. Không dùng `javax.net.debug=ssl:handshake` để chẩn đoán HotSpot thread-local handshakes.

### 12.7. `Thread.stop()` / `Thread.suspend()`

Đây là các API dừng/suspend thread cũ có nhiều rủi ro nghiêm trọng và không phải cách thực hiện JEP 312. **Không dùng trong ví dụ hoặc hướng dẫn mới**. Nếu cần hủy tác vụ ứng dụng, ưu tiên cancellation được thiết kế hợp tác, interrupted status, executor shutdown và timeout phù hợp.

## 13. Ranh giới với Java virtual threads (Java 21+)

Từ Java 21, **virtual threads** là một thành phần chuẩn của nền tảng. Khi nói về cơ chế HotSpot JEP 312, cần tránh suy rằng mỗi `java.lang.Thread` virtual luôn tương ứng một native `JavaThread` chuyên dụng đang chạy liên tục.

Nói ngắn gọn:

- Platform thread thường gắn trực tiếp với một luồng thực thi hệ điều hành và JavaThread của HotSpot.
- Virtual thread có thể **mounted** lên một carrier platform thread khi đang chạy Java code và **unmounted** khi park/block theo điều kiện runtime.
- Vì thế “handshake JavaThread X” và “truy vấn virtual thread V” không phải cùng phép ánh xạ 1–1 đơn giản.
- HotSpot/JVMTI hiện đại có những protocol dành cho mounted/unmounted virtual threads và các công cụ; chi tiết có thể khác giữa các bản JDK.
- Không khẳng định mọi operation nội bộ của Java 10 tự áp nguyên xi lên hàng triệu virtual threads như một tập JavaThreads native.

JEP 312 ra đời **trước** virtual threads. Khi giải thích lịch sử, nên mô tả nền tảng per-JavaThread của Java 10; khi triển khai profiler/JVMTI với virtual threads ở Java 21+, đọc tài liệu version đó và test đúng trạng thái mount/unmount.

**Không dùng mã C++ snapshot của JDK 10 như một bản hợp đồng bất biến cho mọi JDK 21/25.** OpenJDK hiện đại có overload và logic bảo vệ target/virtual thread khác với bản đầu tiên.

## 14. Khi nào VM cần global safepoint dù đã có handshakes?

Không phải công việc VM nào cũng an toàn khi xử lý từng target độc lập.

### 14.1. Bất biến toàn cục

Nếu operation phải nhìn thấy trạng thái toàn heap hoặc VM-wide data structures trong một khoảng bất biến, mỗi thread hoàn thành callback tại một thời điểm khác có thể không đủ. JVM có thể cần:

- global safepoint;
- GC barriers và concurrent protocol;
- snapshot/synchronization phức tạp hơn;
- các trạng thái/locks khác được thiết kế riêng.

**Một handshake trên tất cả luồng không mặc định là stop-the-world.** Dùng sai assumption này có thể dẫn tới đọc dữ liệu race, nhất quán giả hoặc thiết kế profiler không đúng.

### 14.2. Garbage collection

Một số GC/VM operations yêu cầu stop-the-world phases, những việc khác có thể tiến hành concurrent hoặc dùng thread-local handshake cho từng JavaThread. Mỗi collector (G1, ZGC, Shenandoah nếu triển khai hỗ trợ, v.v.) có chiến lược và phiên bản khác nhau.

Không khẳng định JEP 312 “xóa mọi GC pause” hoặc “mọi collector từ Java 10 đều concurrent”. Nó là **một primitive giảm nhu cầu global coordination khi bài toán cho phép**, không phải lời bảo đảm không có STW.

### 14.3. Diagnostic và runtime maintenance

Một số công việc như truy xuất thông tin stack/monitor hoặc bảo trì trạng thái thread có thể hưởng lợi từ phạm vi per-thread. Tuy nhiên, **API public không bắt buộc HotSpot/JVM khác phải dùng handshake**. Thông tin chính xác phải dựa vào tài liệu sản phẩm hoặc mã nguồn phiên bản cụ thể khi nghiên cứu sâu.

## 15. Hiệu năng: tại sao targeted handshakes hữu ích, và không có “miễn phí”

### 15.1. Lợi ích của việc thu hẹp phạm vi

Với N JavaThreads, một global safepoint phải phối hợp các thread theo protocol toàn VM ngay cả khi operation cuối cùng chỉ liên quan B. Một targeted handshake có thể tránh yêu cầu A/C dừng để phục vụ operation của B.

Nếu chỉ cần vài thread của một tập lớn, khả năng giới hạn phạm vi giúp VM có cơ hội giảm global pause pressure, giảm gián đoạn request không liên quan và phục vụ runtime tasks linh hoạt hơn.

### 15.2. Nhưng handshake cũng có chi phí

- Gửi/đặt operation vào trạng thái thread mục tiêu.
- Target polling hoặc handshaker kiểm tra safe state.
- Serialization/lock/queue và completion tracking.
- Kiểm tra lifetime khi target exit.
- Chờ operation ở target chậm nhất nếu yêu cầu tổng hợp nhiều kết quả.
- Có thể tranh chấp với global safepoints/GC operations và các handshake khác.

Đừng khẳng định một tập 100 target sẽ hoàn thành trong thời gian bằng một target. Thời gian có thể bị ảnh hưởng bởi số lượng target, trạng thái của từng thread, độ dài closure và sự tranh chấp.

### 15.3. Đo đúng mục tiêu

Những số liệu hữu ích tùy nhu cầu:

| Metric | Điều nó có thể cho thấy | Giới hạn |
| --- | --- | --- |
| Tail latency của request | Tác động cuối cùng đến người dùng | Nhiều yếu tố không liên quan handshake |
| Pause distribution | Có global pause hoặc không | Không xác nhận từng handshake |
| Safepoint statistics/logs | Các global safepoint cụ thể | Không có nghĩa mọi handshake luôn được log thành safepoint |
| Handshake debug/trace logs | Một số hoạt động handshake theo VM/log tags | Có thể không phát sinh trong demo; log tags phụ thuộc JDK |
| JFR/async profiling | Thời gian thực thi/thứ tự sự kiện | Cần biết semantics của từng event/profiler |
| Thread state/CPU profile | Luồng nào đang chạy/chờ | Không phải trực tiếp nhận dạng closure |

**Đừng đo bằng một lần startup duy nhất rồi nói “JEP 312 nhanh hơn 80%”.** Cần workload, baseline, JDK vendor/build, số threads và nhiều lần đo có thống kê hợp lý.

## 16. Chẩn đoán với HotSpot Unified Logging

Với HotSpot hiện đại, bạn có thể xem danh sách log tag được hỗ trợ:

```bash
java -Xlog:help
```

Nếu runtime của bạn có tag `handshake`, có thể thử trong môi trường chẩn đoán:

```bash
java -Xlog:handshake=debug CooperativeTargetsDemo
```

Hoặc khi cần thông tin chi tiết hơn (nếu runtime thực sự hỗ trợ tag/level):

```bash
java -Xlog:handshake=trace YourMainClass
```

**Phân biệt:**

- `-Xlog:handshake=debug` là **cờ chẩn đoán HotSpot**, không phải lệnh yêu cầu một handshake.
- Demo `CooperativeTargetsDemo` chỉ dùng BlockingQueue của Java; nó **không có nghĩa** bắt buộc tạo log handshake. Trên JDK được kiểm thử, tag `handshake` được liệt kê trong `-Xlog:help` nhưng chạy demo không sinh dòng handshake nội bộ.
- Có thể có runtime JDK khác, VM khác hoặc cấu hình khác nên tag/log format không giống. Hãy kiểm tra `-Xlog:help` trước, không đặt một lệnh log cũ làm điều kiện tính đúng của code ứng dụng.
- Không tự bật logging trace với khối lượng lớn cho mọi service production; nó có thể tốn I/O, log nhạy cảm hoặc ảnh hưởng hiệu năng.
- Để chẩn đoán global safepoint, các tag như `safepoint` liên quan nhưng **khác** handshake, không tự dùng một để suy ra toàn bộ cái kia.

### 16.1. Không có log không chứng minh không có cơ chế

Một chương trình có thể không kích hoạt internal operation cần handshake trong đúng lần chạy, hoặc log level chưa cho thấy event, hoặc một logging path không được dùng. Vì vậy **không có dòng log ≠ implementation không có thread-local handshakes**. Hãy kiểm tra tài liệu, VM version và trace của workload thực tế.

### 16.2. Khi cần kiểm chứng sâu

Nếu đang phát triển HotSpot/JVMTI/native agent, có thể nghiên cứu mã nguồn đúng bản JDK, ví dụ:

- `src/hotspot/share/runtime/handshake.hpp`: closure, target, overload nội bộ.
- `src/hotspot/share/runtime/handshake.cpp`: protocol thực thi.
- `src/hotspot/share/runtime/safepoint.*`: safepoint và handshake safety.
- Mã JVMTI liên quan nếu đang truy vấn thread/stack.

Đây chỉ là **đường dẫn tham khảo trong source OpenJDK**, không phải file dự án cần chỉnh sửa để học Java application development và không phải API ổn định dành cho ứng dụng.

## 17. Vấn đề correctness khi phối hợp một tập target

### 17.1. Không suy thứ tự callback

Với subset `{A,C}`, A có thể hoàn thành trước C hoặc ngược lại. VM subsystem không được tự suy thứ tự từ cách sắp một danh sách đầu vào, trừ khi đã thiết kế serialization/order guarantee.

Nếu cần xử lý kết quả theo thứ tự, requester có thể thu từng kết quả và **sắp/xuất** sau khi chúng hoàn thành, như demo Java in `ra` trước `rc`. Điều đó không có nghĩa hai operation thật luôn chạy đúng thứ tự đó.

### 17.2. Không suy tính đồng thời

Nếu closure A đọc trạng thái lúc t1, closure C đọc lúc t2, dữ liệu có thể thay đổi giữa hai lần. Nếu cần snapshot đồng nhất, phải có protocol giúp đóng băng hoặc version dữ liệu đúng phạm vi.

**All-target handshake không tự cho một ảnh chụp đồng thời của toàn bộ Java heap.**

### 17.3. Nếu target biến mất

Khi một target thoát lúc operation đang chờ, requester có thể phải xử lý “target not alive”, cancellation hoặc completion no-op tùy protocol. Không được giữ raw native pointer mà không bảo vệ lifetime.

Trong code Java, `Thread.isAlive()` cũng chỉ là quan sát tại thời điểm đọc; nó không ngăn target kết thúc ngay sau đó. Khi thiết kế hệ thống user-level, cancellation/timeout/lifetime phải được xử lý đúng.

### 17.4. Một closure có thể đòi điều kiện đặc biệt

Một số operation an toàn khi handshaker khác thực hiện thay target, một số operation có thể cần chính target thực thi. Vì vậy đừng biến mọi callback thành một giao diện “run on target” chung rồi tự cho rằng từng implementation có cùng semantic.

Mã nguồn HotSpot hiện đại biểu diễn khác biệt này trong loại closure/protocol nội bộ. Khi làm với native code thật, phải tuân thủ hợp đồng của phiên bản cụ thể.

### 17.5. Deadlock và lock order

Một operation giữ lock không phù hợp khi chờ target đạt safe state có thể gây deadlock hoặc timeout. Internal handshakes liên quan đến VM locks/thread state; không an toàn nếu tùy ý gọi Java callback blocking trong các ngữ cảnh đó.

Trong chương trình ứng dụng, hãy học từ tinh thần này: không giữ lock rộng hơn cần thiết trong lúc chờ nhiều `CompletableFuture` và không làm thread pool tự chờ nhau trong một pool bị giới hạn. Nhưng **đây là bài học concurrency chung**, không phải API handshake do user gọi.

### 17.6. Timeout phải có chính sách

Một targeted operation không nhất thiết hoàn thành tức thì. Công cụ/vận hành nên có chính sách timeout/cancellation phù hợp; không biến một thread đang kẹt thành lệnh yêu cầu toàn process chờ vô hạn.

Trong ứng dụng Java, `CompletableFuture.orTimeout` hoặc `Future.get(timeout, unit)` có thể được dùng cho **request của chính ứng dụng**. Chúng không đặt timeout cho HotSpot handshake nội bộ mà JVM dùng ở các subsystem của mình.

## 18. Phân biệt internal JavaThread với virtual thread và Thread object

Từ Java 21, virtual threads là một phần nền tảng Java. Một `java.lang.Thread` object có thể đại diện virtual thread, nhưng không phải mọi virtual thread đều giữ một **OS platform thread / HotSpot JavaThread chuyên dụng**.

- Một virtual thread có thể được **mount** trên carrier platform thread khi chạy.
- Nó có thể **unmount** khi blocking/park theo điều kiện runtime.
- JVM tooling và JVMTI xử lý virtual thread có protocol riêng ở những trường hợp thích hợp.
- Một thuật ngữ “chọn thread B” phải xác định đang nói **logical virtual thread**, **carrier platform JavaThread**, hay một native VM thread.
- Không khẳng định một JEP 312 handshake cổ điển luôn nhắm trực tiếp tất cả virtual threads theo tỷ lệ 1–1.

**Đối với public Java 21+ code**, lấy `thread.threadId()` và `ThreadMXBean` như chương trình mục 11 là một ví dụ quản lý thread IDs phù hợp; riêng với virtual threads, khả năng hiển thị của thread management APIs có hạn chế theo tài liệu từng method. Không suy nó làm việc giống hệt platform threads.

Nếu nghiên cứu profiler virtual threads, hãy đọc JDK/JVMTI docs tương ứng và test các trạng thái mounted/unmounted; không dùng hướng dẫn HotSpot năm 2017 như chuẩn triển khai của JDK 25.

## 19. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Thread-local handshake là Java `ThreadLocal`.” | Không: `ThreadLocal` giữ dữ liệu per-thread của ứng dụng; handshake là VM coordination |
| “Có `Thread.handshake()` trong Java 10.” | Không có public Java SE method như vậy |
| “Một handshake luôn dừng mọi thread.” | Không: có thể nhắm một target hoặc nhóm target |
| “Nếu nhắm {A,C}, B luôn phải dừng.” | Không do chính operation này; B có thể vẫn bị ảnh hưởng bởi operation VM khác |
| “All-thread handshakes đồng nghĩa global safepoint.” | Không: per-thread completion không nhất thiết barrier toàn cục |
| “Callback luôn chạy trên target thread.” | Không: VM/initiating thread có thể xử lý khi target ở trạng thái an toàn |
| “Callback có thể chạy ngay cả khi target ở trạng thái bất kỳ.” | Không: phải tuân theo safepoint/handshake-safe protocol |
| “Chọn hai target cho snapshot atomic của chúng.” | Không: thời điểm xử lý có thể khác nhau |
| “Handshake xóa mọi STW GC pause.” | Không: công việc toàn cục vẫn có thể cần safepoint |
| “Handshake luôn tức thì, có giới hạn 1 ms.” | Không có bảo đảm như vậy ở public API |
| “`Thread.join()` là VM handshake.” | Không: nó đợi thread kết thúc |
| “`Thread.interrupt()` là VM handshake.” | Không: nó báo interrupt theo API ứng dụng |
| “`CountDownLatch` là cơ chế mà HotSpot JEP 312 gọi trực tiếp.” | Không: nó là coordination primitive của Java application |
| “`Thread.onSpinWait()` buộc JVM xử lý handshake.” | Không: đó là hint cho spin-wait |
| “`Thread.State.WAITING` luôn handshake-safe với mọi closure.” | Không: Java Thread.State không đủ diễn tả internal VM state |
| “Mỗi Java 21 virtual thread có một native JavaThread riêng.” | Không: virtual threads có carrier/mount-unmount |
| “`ThreadMXBean.getThreadInfo` chính là `Handshake::execute`.” | Không phải hợp đồng API; implementation có thể khác |
| “Có tag `-Xlog:handshake` là demo Java tự gọi handshake.” | Không: flag chỉ cho phép log khi runtime có event |
| “Cờ `-XX:ThreadLocalHandshakes` từ Java 10 phải dùng ở mọi JDK mới.” | Không: cờ lịch sử có thể không được hỗ trợ; tránh copy legacy tuning |
| “Càng nhiều target, càng chắc rẻ hơn global safepoint.” | Không bảo đảm: phụ thuộc mục tiêu, latency và protocol |
| “Một operation nhắm target chết sẽ tự chuyển sang thread cùng tên.” | Không: identity/lifetime phải được bảo vệ |
| “JEP 312 là public API cho arbitrary Runnable ở VM-safe state.” | Không: closure nội bộ có điều kiện và hạn chế riêng |
| “Không có handshake log nghĩa là JVM không hỗ trợ.” | Không: demo có thể không kích hoạt event hoặc logging chưa phù hợp |

## 20. Bài tập tự kiểm tra kèm đáp án

### Bài 1 — Một target

A, B, C đang chạy. Một internal operation chỉ cần trạng thái B. Handshake per-thread có ý nghĩa gì?

**Đáp án:** VM có thể hướng yêu cầu tới B trong trạng thái an toàn phù hợp mà không buộc A/C tham gia global barrier **chỉ vì operation này**. A/C vẫn có thể gặp safepoint/handshake khác từ subsystem khác.

### Bài 2 — Tập target

Bạn cần xử lý A và C, không cần B. Có thể hiểu “tập target” như thế nào?

**Đáp án:** mỗi target được phối hợp theo safe-state protocol, completion riêng được ghi nhận/tổng hợp. Không tự giả định callback của A và C xảy ra đồng thời hoặc có một public `Thread.handshake(Set)`.

### Bài 3 — All target

Một operation hướng đến tất cả JavaThreads. Nó có chắc là global safepoint không?

**Đáp án:** không. All-thread handshake có thể cho các thread hoàn thành callback và tiếp tục theo thời điểm riêng. Global safepoint là một protocol khác cần rào chắn toàn VM.

### Bài 4 — Callback execution context

Khi B đang blocked trong safe state, callback bắt buộc chạy trên B?

**Đáp án:** không. HotSpot có thể cho VMThread hoặc initiating thread làm thay B theo tính chất closure/protocol, trong khi B tiếp tục bị giữ blocked an toàn.

### Bài 5 — Dữ liệu nhất quán

H(A) xong lúc t1 và H(C) xong lúc t2. Có chắc dữ liệu đọc từ A/C là snapshot cùng lúc?

**Đáp án:** không. Muốn snapshot có bất biến toàn cục cần protocol bổ sung hoặc safepoint phù hợp.

### Bài 6 — Demo Java

Chương trình `CooperativeTargetsDemo` in:

```text
single=B
afterSingle=0,1,0
subset=[A, C]
afterSubset=1,1,1
```

Điều đó chứng minh gì?

**Đáp án:** user-level queue đã định tuyến request đến B rồi đến A/C và không gửi request mới cho B. Nó **không chứng minh** nội bộ HotSpot đã chạy JEP 312 handshake cho những mailbox operations.

### Bài 7 — API public

`ThreadMXBean.getThreadInfo(long[], int)` có thể trả thông tin đúng hai thread. Có thể tuyên bố Java SE bắt buộc dùng thread-local handshake cho method này không?

**Đáp án:** không. Đây là public management API với output contract riêng; HotSpot/JVM có quyền chọn implementation phù hợp.

### Bài 8 — Virtual thread

Trong Java 21+, một virtual thread có một dedicated OS thread trong toàn bộ đời sống?

**Đáp án:** không. Virtual thread có thể mount/unmount trên carrier platform thread. Khi giải thích handshakes phải phân biệt logical virtual thread với JavaThread native.

### Bài 9 — Thread interrupt

`t.interrupt()` có thể làm gì, và vì sao không phải JEP 312 handshake?

**Đáp án:** nó báo interrupt theo API Java, có thể làm blocking operation ném `InterruptedException` hoặc đặt flag; không cung cấp internal VM-safe callback mechanism.

### Bài 10 — Thread exit

Một requester đã chọn target B, sau đó B kết thúc trước khi operation hoàn thành. Điều nào cần được xử lý?

**Đáp án:** target lifetime, cancellation/completion và việc không dùng stale pointer; không tự áp operation sang một thread khác có cùng tên.

### Bài 11 — Safepoint và latency

JEP 312 cho phép per-thread operation nhưng có cam kết tất cả operation hoàn thành trong 1 ms không?

**Đáp án:** không. Polling, native/blocked state, locks, workload và VM protocol ảnh hưởng latency.

### Bài 12 — Cờ debug

`java -Xlog:handshake=debug CooperativeTargetsDemo` không sinh dòng log handshake. Có chắc JDK không có JEP 312 không?

**Đáp án:** không. Demo chỉ dùng BlockingQueue và có thể không kích hoạt một handshake có log ở mức debug. Trước hết xem `java -Xlog:help`, thử workload thực và phân biệt logging với chính request nội bộ.

### Bài 13 — Global operation

Một subsystem cần bất biến đồng thời của dữ liệu toàn heap. Có thể thay global safepoint bằng những handshake độc lập chỉ vì có JEP 312?

**Đáp án:** không. Thay đổi protocol đòi bảo đảm correctness tương đương, có thể cần global safepoint hoặc đồng bộ concurrent được thiết kế đặc biệt.

### Bài 14 — Nhận dạng target

Nếu cần chọn một tập thread cho diagnostic, nên dựa vào tên thread làm identity vĩnh viễn không?

**Đáp án:** không. Tên có thể trùng, thread có thể chết hoặc được tạo lại; dùng identity/lifetime được API quản lý, không tự dùng tên hoặc raw native pointer vượt đời sống thread.

### Bài 15 — Đo performance

Bạn có một log safepoint ít hơn sau nâng JDK. Có thể khẳng định toàn bộ cải thiện đến từ JEP 312 không?

**Đáp án:** chưa. Nâng JDK có nhiều thay đổi GC/JIT/runtime. Cần benchmark đối chứng, log đúng event và workload để xác định nguyên nhân.

### Bài 16 — Version hiện đại

Một tài liệu năm 2018 hướng dẫn bật `-XX:ThreadLocalHandshakes`. Có nên áp ngay vào JDK 25 production?

**Đáp án:** không. Cờ VM nội bộ có thể bị thay đổi hoặc loại bỏ. Cơ chế vẫn hữu ích, nhưng không dùng cờ legacy nếu runtime hiện tại không tài liệu hóa/hỗ trợ; kiểm tra đúng phiên bản HotSpot.

## 21. Checklist cho người học và người phát triển tooling

1. **Đã hiểu JEP 312 là VM-internal enhancement của Java 10 chưa?**
2. **Đã phân biệt JavaThread native với `java.lang.Thread` và virtual thread chưa?**
3. **Đang yêu cầu một target, subset hay tất cả?**
4. **Target nào thực sự cần operation?** Đừng mở rộng toàn VM khi không cần.
5. **Mỗi target có trạng thái handshake-safe phù hợp không?**
6. **Closure có thể chạy trên thread khác thay target không?**
7. **Có định nghĩa completion/cancellation khi target chết không?**
8. **Có hiểu không bảo đảm thứ tự giữa các target không?**
9. **Có cần snapshot atomic hay chỉ từng kết quả per-thread?**
10. **Nếu cần global invariants, đã cân nhắc safepoint hoặc protocol khác chưa?**
11. **Có chi phí polling, queue/lock và chờ target chậm nhất không?**
12. **Có tránh claim handshake luôn nhanh hơn global safepoint không?**
13. **Có tránh sửa HotSpot internal code khi chỉ viết ứng dụng Java không?**
14. **Có phân biệt ví dụ mailbox Java với handshake thật không?**
15. **Có dùng public management APIs đúng hợp đồng mà không đoán implementation không?**
16. **Có tránh `Thread.stop()/suspend()` và flags legacy không?**
17. **Có kiểm tra log tag bằng `java -Xlog:help` trước khi thử không?**
18. **Có tránh nhầm `-Xlog:handshake` là lệnh kích hoạt handshake không?**
19. **Có phân biệt global safepoint log với per-thread handshake log không?**
20. **Có thiết kế timeout/cleanup cho requests ở tầng ứng dụng không?**
21. **Có kiểm tra correct lifecycle khi một thread thoát?**
22. **Có đo tail latency/throughput với workload thực và JDK version rõ không?**
23. **Có xem version mới nếu đang nói tới virtual thread/JVMTI hiện đại không?**
24. **Có tách ThreadMXBean target selection với internal VM protocol không?**
25. **Có bảo đảm các kết luận về GC không vượt hợp đồng của collector cụ thể không?**

## 22. Tổng kết

**Thao tác phối hợp hướng đến một luồng hoặc một tập luồng** trong JEP 312 cho HotSpot một công cụ an toàn để xử lý công việc **theo JavaThread**, thay vì luôn yêu cầu mọi thread đi vào global safepoint. Với một target, VM nhắm đúng thread cần xử lý. Với nhiều target, từng operation có thể được hoàn thành theo thời điểm riêng; các thread ngoài tập không phải dừng do chính operation đó. Với all-thread handshake, “tất cả đều có callback” **không đồng nghĩa** mọi thread đều bị giữ ở một barrier toàn cục.

Callback chỉ được thực hiện theo protocol **handshake-safe**, có thể bởi target hoặc một handshaker/VMThread phù hợp; polling, blocked state và lifecycle khiến latency không được cam kết tức thì. Cơ chế vẫn hữu ích trong HotSpot hiện đại, nhưng **không phải public Java SE API**. Các ví dụ Java 17+/21+ minh họa việc chọn target và quan sát subset, **không trực tiếp gọi JEP 312**.

Khi nghiên cứu sâu, hãy dựa trên JEP 312, JDK/HotSpot đúng phiên bản và log phù hợp; tránh các cờ cũ, tránh suy rằng mọi virtual thread là một native JavaThread, và không thay global safepoint bằng per-thread handshakes nếu bài toán thật sự cần bất biến toàn VM.

### Tài liệu tham khảo chính thức và nguồn nghiên cứu

- [JEP 312 — Thread-Local Handshakes](https://openjdk.org/jeps/312)
- [OpenJDK HotSpot — handshake.hpp (mã nguồn hiện đại)](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/handshake.hpp)
- [OpenJDK HotSpot — handshake.cpp (mã nguồn hiện đại)](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/handshake.cpp)
- [OpenJDK HotSpot — safepoint.hpp](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/safepoint.hpp)
- [Oracle Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [Oracle Java SE 21 — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html)
- [Oracle Java SE 17 — java command and Unified Logging](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
- [JEP 444 — Virtual Threads (Java 21)](https://openjdk.org/jeps/444)
- [JDK implementation notes — Java Threads](https://docs.oracle.com/en/java/javase/21/core/java-threads.html)