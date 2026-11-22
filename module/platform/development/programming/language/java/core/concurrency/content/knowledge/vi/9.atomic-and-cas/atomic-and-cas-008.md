# ABA problem và AtomicStampedReference trong Java Concurrency

> **Phạm vi:** Java concurrency nói chung, thuộc chủ đề **Atomic & CAS**. Bài giải thích hiện tượng ABA, trường hợp ABA có thể phá tính đúng đắn của thuật toán lock-free, cơ chế ghép reference với stamp của `AtomicStampedReference`, cách viết CAS loop và những giới hạn thiết kế cần kiểm chứng. Không đi vào các API riêng của Spring.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Mô tả chính xác **compare-and-set (CAS)** kiểm tra điều gì và vì sao CAS thông thường không ghi nhận toàn bộ lịch sử của giá trị.
- Phân tích chuỗi thay đổi **A → B → A** và nhận ra khi nào một thread dùng snapshot cũ vẫn có thể CAS thành công.
- Phân biệt **ABA có xảy ra** với **ABA gây lỗi**: không phải mọi lần giá trị trở lại A đều làm chương trình sai.
- Giải thích `AtomicStampedReference<V>` lưu logic một **cặp (reference, int stamp)** và kiểm tra cả hai khi CAS.
- Sử dụng `get(int[] stampHolder)` để đọc reference và stamp thành **một snapshot nhất quán**, thay vì đọc tách hai thành phần trong lúc các thread khác cập nhật.
- Viết đúng `compareAndSet(expectedReference, newReference, expectedStamp, newStamp)`, đặt stamp mới theo một quy ước monotonic/unique phù hợp.
- Hiểu vì sao **stamp không tự bảo vệ mutable object nội bộ**, không thay thế memory reclamation, không làm nhiều state ngoài cặp trở nên atomic, và vẫn có nguy cơ tái sử dụng stamp.
- Viết bài thử nghiệm Java 17 có lịch thực thi kiểm soát để quan sát ABA với `AtomicReference` và cách `AtomicStampedReference` chặn một cập nhật dựa trên phiên bản cũ.

**Thông điệp chính:** CAS thường trả lời “giá trị hiện tại có bằng giá trị tôi đã đọc không?”. Nhưng nhiều thuật toán thực sự cần câu hỏi mạnh hơn: **“đây có còn là cùng một thế hệ/trạng thái mà tôi đã đọc không?”**. Stamp cung cấp thêm tín hiệu phiên bản để phát hiện thay đổi trung gian mà kiểm tra giá trị cuối đơn thuần bỏ lỡ.

## 2. Ôn lại CAS trước khi nói đến ABA

CAS là một thao tác read-check-write nguyên tử ở cấp biến atomic được API quy định. Ý tưởng:

```text
compareAndSet(expected, update):

    nếu current vẫn bằng expected:
        current = update
        trả true
    ngược lại:
        giữ nguyên current
        trả false
```

`AtomicReference<V>` là lớp Java SE dùng CAS trên **một tham chiếu object**. Ví dụ:

```java
AtomicReference<String> state = new AtomicReference<>("A");
boolean changed = state.compareAndSet("A", "B");
```

Đây là **đoạn minh họa**, cần import `java.util.concurrent.atomic.AtomicReference`. Với reference CAS, phép so sánh là **reference identity (`==`)**, không phải `String.equals()`. Ví dụ dùng string literal để trực quan, nhưng ứng dụng thực phải hiểu identity của từng object; trong ví dụ chạy đầy đủ ở dưới ta chủ động tạo các object `A`, `B` và `C` riêng, giữ cùng reference trong suốt lần thử.

CAS giải quyết **atomicity của một lần cập nhật**: giữa lúc kiểm tra expected và ghi update, thread khác không thể chen một cập nhật lên cùng biến atomic. Nhưng CAS **không lưu các trạng thái đã diễn ra trước đó**. Nếu giá trị hiện tại một lần nữa bằng expected, CAS thông thường có thể coi điều kiện thành công, dù đã có nhiều cập nhật ở giữa.

### Ví dụ CAS loop

```java
// Đoạn minh họa bên trong một method:
// ref là AtomicReference<State> đã được khởi tạo;
// transform(State) trả về trạng thái mới, không gây side effect.
for (;;) {
    State observed = ref.get();
    State next = transform(observed);
    if (ref.compareAndSet(observed, next)) {
        break;
    }
}
```

Đây là **mã minh họa, không phải chương trình độc lập**: `State`, `ref` và `transform()` cần được định nghĩa. Vòng lặp thử lại vì có thể thread khác thay đổi reference trước CAS của chúng ta.

**Lưu ý quan trọng:** vòng lặp CAS thất bại rồi thử lại giúp xử lý nhiều cuộc đua thông thường, nhưng **không tự giải quyết ABA**. Trong trường hợp giá trị đã đi A→B→A, CAS cũ **không thất bại**; không có cơ hội tự retry.

## 3. ABA problem: A → B → A

Giả sử thread T1 đọc tham chiếu hiện tại là A rồi chuẩn bị cập nhật. Trước khi T1 thực hiện CAS, thread T2 thay đổi A→B, sau đó B→A.

```text
Thời điểm             Thread T1                    Thread T2
-------------------   ---------------------------- --------------------------------
t0                    đọc current = A
t1                                                 CAS A -> B thành công
t2                                                 CAS B -> A thành công
t3                    CAS(expected=A, update=C)
t4                    -> thành công vì current=A
```

Ở t3, kiểm tra reference identity vẫn đúng: **giá trị cuối trỏ lại cùng object A**. CAS không phân biệt trạng thái A ở t0 với trạng thái A ở t2. Đây là hiện tượng **ABA**.

Nếu T1 chỉ cần đặt giá trị C **miễn current đang là A**, có thể kết quả vẫn đúng. Nhưng nếu T1 đã đưa ra một quyết định dựa trên giả định **“không có ai thay đổi state kể từ khi tôi quan sát”**, thì CAS thành công là tín hiệu **quá yếu**.

### ABA không đồng nghĩa với data race kiểu truy cập biến không đồng bộ

Với `AtomicReference`, mỗi lần đọc/CAS trên reference vẫn có memory semantics atomic đúng theo API. ABA có thể xảy ra **dù mọi truy cập biến atomic đều được đồng bộ đúng**.

Vì thế:

- **Data race / thiếu happens-before** là một loại vấn đề memory model.
- **ABA** thường là một vấn đề **logic/versioning** của thuật toán optimistic/lock-free: dữ liệu hiện tại có thể bằng dữ liệu đã đọc, nhưng lịch sử thay đổi khiến suy luận cũ không còn hợp lệ.
- Dùng `volatile` hay bảo đảm visibility đơn thuần **không khôi phục được lịch sử thay đổi** nếu chỉ giữ một giá trị.
- Một CAS thành công bảo đảm atomicity của chính thao tác CAS, **không bảo đảm** phần dữ liệu phụ thuộc đã được T1 quan sát trước đó vẫn hợp lệ.

## 4. Khi ABA thực sự nguy hiểm?

### Tình huống lock-free stack (mô hình)

Giả sử stack dùng một `AtomicReference<Node> head` và mỗi node có trường `next`:

```text
Trước:
head -> A -> B -> C

Thread T1:
  đọc oldHead = A
  đọc next = B
  chuẩn bị CAS(head, A, B)

Thread T2:
  pop A
  pop B
  push lại cùng object A (next của A giờ là C)
  head lại là A

Thread T1:
  CAS(head, A, B) thành công
```

T1 vẫn có reference A đúng identity nên CAS có thể thành công, nhưng nó sử dụng **next=B đã đọc từ thế hệ cấu trúc cũ**. Trong khi đó B có thể đã bị loại khỏi stack, nên việc đặt head=B có thể làm hỏng cấu trúc logic, làm mất node hoặc đưa node không còn hợp lệ vào stack.

Đây là **sơ đồ khái niệm**, không phải triển khai stack lock-free hoàn chỉnh. Các phiên bản thực tế cần cân nhắc việc node được tái sử dụng, ràng buộc mutation của `next`, publication, tiến triển, memory reclamation và chứng minh tính linearizable của toàn bộ thuật toán.

**Điểm gây lỗi không phải chỉ vì head quay lại A.** Điểm gây lỗi là T1 đang dùng **thông tin phụ thuộc vào một thế hệ cấu trúc đã thay đổi**, trong khi CAS chỉ xác minh một reference head.

### Một tình huống khác: trạng thái workflow

Giả sử trạng thái một công việc đang là `READY`. T1 đọc READY và quyết định thực hiện bước X sau khi tính toán chậm. Trong thời gian đó T2 chuyển READY→RUNNING→READY cho một vòng xử lý mới. T1 dùng CAS READY→RUNNING rồi nghĩ mình đã “đặt lock” cho vòng ban đầu. Nếu xử lý yêu cầu liên kết với đúng **lượt công việc**, cần một version/generation; chỉ kiểm tra enum READY là chưa đủ.

Ở tình huống này, đôi khi cách tốt hơn là mô hình hóa state có **generation ID** bất biến, chứ không nhất thiết dùng `AtomicStampedReference`. Cần lựa chọn theo invariant thực sự.

## 5. Java giải quyết kiểu ABA này như thế nào?

`AtomicStampedReference<V>` thuộc `java.util.concurrent.atomic`. Nó quản lý **một cặp logic**:

```text
(reference, stamp)
```

Trong đó:

- `reference` là tham chiếu đến object V.
- `stamp` là số nguyên `int` do **người viết chương trình** quy định ý nghĩa, thường được dùng làm version/generation.
- Thao tác CAS kiểm tra **cả expectedReference và expectedStamp**, rồi cập nhật **cả newReference và newStamp** như một thao tác atomic trên cặp.

Tạo biến:

```java
AtomicStampedReference<String> state =
        new AtomicStampedReference<>(initialReference, 0);
```

Đây là **đoạn minh họa trong một method hoặc field initializer**, cần import `java.util.concurrent.atomic.AtomicStampedReference`; `initialReference` là biến đã có.

Trình tự thay đổi:

```text
Trước:  (A, 0)
T2:     (A, 0) -> (B, 1)
T2:     (B, 1) -> (A, 2)
T1:     muốn CAS từ (A, 0) sang (C, 1)

Kết quả: FAIL, vì current = (A, 2), không còn là (A, 0).
```

Mặc dù reference cuối vẫn là A, **version đã khác**. Nếu T1 thực sự muốn cập nhật thế hệ mới, nó phải **đọc lại cặp (A, 2), tính lại bước tiếp theo theo dữ liệu mới**, rồi thử CAS mới.

### Ý nghĩa của tên “StampedReference”

Đừng hiểu stamp là “tự phát sinh” hay một mã thời gian của hệ điều hành. `AtomicStampedReference` **không tự cộng stamp**: mọi lần `compareAndSet` hoặc `set` cần caller cung cấp stamp mới. Nếu caller tái dùng stamp cũ hoặc reset về 0, ABA có thể quay trở lại.

Một convention thường gặp:

```text
current = (reference, version)
successful logical mutation:
    nextVersion = version + 1
    CAS(currentReference, nextReference, version, nextVersion)
```

Convention này cần được áp dụng **trên mọi đường cập nhật liên quan**. Các đường `set()`, `attemptStamp()` và logic retry phải cùng tuân thủ chính sách versioning. Không coi `int` version là duy nhất vĩnh viễn: `int` có thể tràn số và quay lại giá trị cũ sau đủ nhiều lần tăng, hoặc bị người gọi chủ động tái sử dụng.

## 6. Các API cốt lõi của AtomicStampedReference

| API | Vai trò | Điều cần ghi nhớ |
|---|---|---|
| `new AtomicStampedReference<>(initialRef, initialStamp)` | Khởi tạo cặp | `initialStamp` hoàn toàn do caller chọn |
| `getReference()` | Lấy reference hiện tại | Chỉ lấy một thành phần tại thời điểm gọi |
| `getStamp()` | Lấy stamp hiện tại | Chỉ lấy một thành phần tại thời điểm gọi |
| `get(int[] stampHolder)` | Lấy reference và ghi stamp vào `stampHolder[0]` | **Cách nên dùng để lấy snapshot cặp nhất quán** |
| `compareAndSet(expectedRef, newRef, expectedStamp, newStamp)` | Atomic CAS cho cặp | So sánh reference bằng **identity** và stamp bằng giá trị số nguyên |
| `set(newRef, newStamp)` | Đặt cặp mới | Không kiểm tra expected; caller phải tự bảo đảm policy/version |
| `attemptStamp(expectedRef, newStamp)` | Thử thay stamp nếu current reference là expectedRef | Hữu ích khi thật sự muốn đổi version mà không đổi reference |
| `weakCompareAndSet(...)` | API CAS yếu | Với API Java 17 của lớp này, xem đặc tả cụ thể; không mặc định thay bằng nó để bảo đảm tiến triển hay hiệu năng |

**Điểm cần đặc biệt nhớ:** `getReference()` rồi `getStamp()` là **hai lệnh riêng**. Nếu thread khác cập nhật ở giữa, bạn có thể tạo ra một cặp expectedReference/stamp **chưa từng tồn tại đồng thời**. Dùng `get(stampHolder)` để lấy cặp từ cùng một snapshot.

Ví dụ:

```java
int[] holder = new int[1];
String expectedRef = stamped.get(holder);
int expectedStamp = holder[0];

// Tính trạng thái kế tiếp từ cùng một snapshot:
String desiredRef = nextReference(expectedRef);
int desiredStamp = expectedStamp + 1;

boolean success = stamped.compareAndSet(
        expectedRef, desiredRef, expectedStamp, desiredStamp);
```

Đây là **đoạn minh họa trong method**, `stamped` và `nextReference()` đã được khai báo ở bên ngoài. `holder` cần có ít nhất một phần tử; với `get`, Java ghi stamp vào chỉ số 0.

Một CAS **thất bại** không phải là lỗi runtime: có thể thread khác vừa cập nhật cặp. Ứng dụng thường đọc lại state, tính lại desired và thử tiếp nếu contract cho phép, hoặc trả kết quả “conflict” cho caller.

## 7. Ví dụ Java 17 chạy độc lập: ABA với AtomicReference và AtomicStampedReference

Để tránh phụ thuộc vào “scheduler có vô tình tạo ra ABA không”, chương trình dưới đây **chủ động sắp thứ tự bằng `Thread.join()`**:

1. Thread chính giữ snapshot cũ.
2. Thread khác hoàn thành A→B→A rồi kết thúc.
3. Thread chính mới thực hiện CAS với snapshot cũ.
4. Lặp lại quy trình với cặp có stamp.

Chúng ta dùng **ba object `String` khác nhau** và so sánh bằng reference identity để tránh hiểu nhầm giữa `==` và `equals()`. Việc `join()` hoàn thành giúp bảo đảm thread chính quan sát cập nhật của worker sau khi worker kết thúc.

Tạo file **`AbaStampedDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.atomic.AtomicStampedReference;

public class AbaStampedDemo {
    private static final String A = new String("A");
    private static final String B = new String("B");
    private static final String C = new String("C");

    public static void main(String[] args) throws InterruptedException {
        AtomicReference<String> plain = new AtomicReference<>(A);
        String oldReference = plain.get();
        Thread firstChanger = new Thread(() -> {
            if (!plain.compareAndSet(A, B) || !plain.compareAndSet(B, A)) {
                throw new AssertionError("unexpected plain CAS failure");
            }
        });
        firstChanger.start();
        firstChanger.join();

        System.out.println("plainBackToA=" + (plain.get() == A));
        System.out.println("plainStaleCas=" + plain.compareAndSet(oldReference, C));
        System.out.println("plainNowC=" + (plain.get() == C));

        AtomicStampedReference<String> stamped = new AtomicStampedReference<>(A, 0);
        int[] stampHolder = new int[1];
        String originalReference = stamped.get(stampHolder);
        int originalStamp = stampHolder[0];

        Thread secondChanger = new Thread(() -> {
            if (!stamped.compareAndSet(A, B, 0, 1)
                    || !stamped.compareAndSet(B, A, 1, 2)) {
                throw new AssertionError("unexpected stamped CAS failure");
            }
        });
        secondChanger.start();
        secondChanger.join();

        System.out.println("stampedBackToA=" + (stamped.getReference() == A));
        System.out.println("stampedVersion=" + stamped.getStamp());
        System.out.println("stampedStaleCas="
                + stamped.compareAndSet(originalReference, C, originalStamp, originalStamp + 1));

        int[] latestStampHolder = new int[1];
        String latestReference = stamped.get(latestStampHolder);
        boolean freshCas = stamped.compareAndSet(
                latestReference, C, latestStampHolder[0], latestStampHolder[0] + 1);

        System.out.println("stampedFreshCas=" + freshCas);
        System.out.println("stampedFinalVersion=" + stamped.getStamp());
    }
}
```

Biên dịch/chạy với JDK 17 hoặc mới hơn:

```bash
javac --release 17 AbaStampedDemo.java
java AbaStampedDemo
```

**Stdout đã biên dịch và chạy kiểm chứng:**

```text
plainBackToA=true
plainStaleCas=true
plainNowC=true
stampedBackToA=true
stampedVersion=2
stampedStaleCas=false
stampedFreshCas=true
stampedFinalVersion=3
```

### Giải thích từng phần

**Phần `AtomicReference`:**

- T1/main đọc `oldReference = A`.
- Worker dùng CAS để chuyển **chính object reference** A→B→A. Hai lần CAS thành công; sau `join()`, current lại là object A.
- `plain.compareAndSet(oldReference, C)` trả `true` vì CAS chỉ thấy reference A đúng identity ở thời điểm cập nhật. **Nó không biết đã từng tồn tại B.**
- Kết quả `plainNowC=true` chỉ cho thấy CAS đã được thực hiện thành công; nếu hợp đồng thuật toán cần phát hiện mọi thay đổi kể từ lúc đọc, điều kiện này còn thiếu.

**Phần `AtomicStampedReference`:**

- T1 đọc đồng thời `(originalReference=A, originalStamp=0)` bằng `get(holder)`.
- Worker làm `(A,0) → (B,1) → (A,2)`.
- T1 thử `compareAndSet(A, C, 0, 1)`. Reference hiện tại đúng A, nhưng stamp hiện tại là 2, **khác expected stamp 0**, nên trả `false`.
- T1 đọc lại `(A,2)` rồi thực hiện một CAS mới với expected stamp 2 và desired stamp 3. Lần này thành công vì **không có thread khác chen vào** giữa snapshot mới và CAS mới trong ví dụ.
- `stampedFinalVersion=3` là kết quả của chính convention tăng version ta chọn, **không phải vì lớp tự động tăng stamp**.

**Vì sao ví dụ dùng `join()`?** Khi cần minh họa hai lịch rõ ràng, nó cho phép worker hoàn thành ABA trước khi main CAS. Trong workload thực, ABA xảy ra do các thread xen kẽ; ta không thể dựa vào lịch quan sát tự nhiên để luôn thấy tình huống ấy. Việc đặt các checkpoint như vậy là kỹ thuật thử nghiệm, không phải hướng dẫn triển khai thuật toán lock-free.

**Lưu ý về exception bên trong Thread:** nếu điều kiện `AssertionError` trong lambda bất ngờ xảy ra, `join()` không tự ném lại lỗi cho main như `Future.get()`; trong demo này ta đã chạy kiểm chứng đúng cả hai CAS của worker. Test production cần kênh báo lỗi rõ, ví dụ `Future` hoặc capture `Throwable` để assertion có thể fail cả test.

## 8. Cách viết vòng lặp stamped CAS an toàn về mặt logic

Khi muốn tính trạng thái mới từ reference đã đọc, mẫu phổ biến:

```java
// Minh họa trong một method: ref là AtomicStampedReference<State>.
// computeNext(State) chỉ tính toán, không gây side effect.
for (;;) {
    int[] stampBox = new int[1];
    State observed = ref.get(stampBox);
    int seenVersion = stampBox[0];

    State next = computeNext(observed);
    int nextVersion = seenVersion + 1;

    if (ref.compareAndSet(observed, next, seenVersion, nextVersion)) {
        break;
    }
    // Cặp đã thay đổi: đọc lại và tính next dựa trên snapshot mới.
}
```

Đây là **code minh họa**, không phải chương trình độc lập; `State`, `ref` và `computeNext()` cần có trong class. Với các thuật toán phức tạp, phải phân tích riêng tính đúng đắn của `computeNext`, quan hệ giữa state ngoài reference và reference CAS, chính sách reuse phiên bản, và cách đối phó contention.

### Không đặt side effect không thể lặp vào CAS loop

Ví dụ không an toàn về ý định:

```java
// Minh họa sai: side effect có thể chạy nhiều lần khi CAS fail.
for (;;) {
    int[] stampBox = new int[1];
    State s = ref.get(stampBox);
    sendEmail(); // Có thể gửi lặp nếu nhiều lần CAS thất bại!
    if (ref.compareAndSet(s, update(s), stampBox[0], stampBox[0] + 1)) {
        break;
    }
}
```

Đây là **đoạn minh họa lỗi**; `State`, `ref`, `sendEmail()`, `update()` thuộc ngữ cảnh ngoài. CAS loop có thể retry nhiều lần nên những side effect như gửi email, gọi API có phí, trừ tài khoản ngoài JVM hoặc ghi log audit cần xử lý riêng qua transaction/idempotency/commit protocol.

Mẫu tốt hơn là tính `next` thuần túy, CAS, rồi **sau khi thành công** kích hoạt side effect với cơ chế chống trùng/lỗi riêng. Ngay cả làm side effect sau CAS cũng không khiến thao tác ngoài JVM trở thành atomic cùng CAS: thread/process có thể crash giữa hai bước, nên cần giải pháp outbox/idempotency hoặc transaction khi bài toán yêu cầu.

### Không tự suy ra progress/fairness

`AtomicStampedReference` giúp tránh một lớp false-success CAS, nhưng không bảo đảm thread cụ thể cuối cùng sẽ thành công. Dưới contention rất cao, một thread có thể retry lâu. **Lock-free algorithm** là thuộc tính của **toàn thuật toán**, không phải thuộc tính suy ra từ việc có một AtomicStampedReference trong code. Một thuật toán dùng atomic nhưng gọi blocking I/O, chờ condition hoặc có vòng phụ thuộc vẫn có thể không lock-free.

## 9. Đọc snapshot đúng: `get(holder)` thay vì hai lệnh riêng

Một lỗi khó thấy:

```java
// Minh họa nguy cơ snapshot không nhất quán.
State refSnapshot = stamped.getReference();
int stampSnapshot = stamped.getStamp();
```

Đây là code minh họa, `stamped` là `AtomicStampedReference<State>`. Giữa hai lệnh, thread khác có thể đổi cặp:

```text
Trước:          (A, 10)
T1 getReference -> A
T2 cập nhật:   (B, 11)
T1 getStamp     -> 11

T1 thu được (A, 11), dù chưa hề tồn tại cặp đó trong khoảnh khắc đã quan sát.
```

T1 có thể làm suy luận sai trước cả khi CAS. Nếu nó CAS, thường CAS sẽ thất bại vì cặp ghép tạm không khớp, nhưng **không nên dựa vào CAS fail để sửa cách đọc state đã lệch**.

Mẫu đúng:

```java
int[] stampBox = new int[1];
State refSnapshot = stamped.get(stampBox);
int stampSnapshot = stampBox[0];
```

Cả hai giá trị phản ánh **cùng một snapshot logic** theo hợp đồng `get(int[])`. Nếu T2 đổi sau khi T1 đọc, CAS với expected pair cũ sẽ thất bại miễn chính pair đó chưa bị tái tạo.

**Lưu ý:** đây không phải snapshot atomic của mọi field bên trong `State`. Nếu `State` là object mutable mà thread khác đang sửa field của nó, `get(holder)` chỉ chụp **reference và stamp**; nó không đóng băng object graph.

## 10. So sánh identity với equality

`AtomicReference.compareAndSet()` và `AtomicStampedReference.compareAndSet()` kiểm tra **reference identity**, tức cùng một object, chứ không gọi `equals()`. Ví dụ:

```java
String a1 = new String("A");
String a2 = new String("A");

System.out.println(a1.equals(a2)); // true
System.out.println(a1 == a2);      // false
```

Đoạn trên có thể đặt trong method main bất kỳ, không cần import. Nếu `AtomicStampedReference<String>` đang giữ `a1`, thì:

```java
// Minh họa với stamped giữ (a1, 5).
boolean ok = stamped.compareAndSet(a2, a1, 5, 6);
// ok == false: a2 không cùng identity với a1.
```

Đây là **đoạn minh họa** với `stamped`, `a1`, `a2` đã khai báo. Stamp khớp nhưng reference **không khớp**. Trong ví dụ chạy chính, ta cố ý giữ A/B/C thành ba object riêng và sử dụng cùng instance A khi quay về, để hiện tượng ABA xảy ra theo nghĩa CAS reference identity.

**Không dùng object wrapper mới một cách tùy tiện** rồi cho rằng “giá trị A trở lại A” sẽ đủ để gây ABA trên `AtomicReference`. Đối với reference CAS, cần current quay về **chính object reference** được quan sát, hoặc cần thiết kế khác có cùng token value. Trong thực tế lock-free structure, việc **tái sử dụng node/reference** làm ABA nguy hiểm.

## 11. Stamp không tự động bảo vệ object bên trong

Ví dụ:

```java
final class MutablePayload {
    int amount;
}

// Minh họa: ref đang giữ một MutablePayload cùng stamp=4.
// Thread T2 giữ chính payload và làm payload.amount = 999
// nhưng KHÔNG thay cặp trong AtomicStampedReference.
```

Đây là class và mô tả minh họa. T1 có thể đọc reference/stamp `(payload,4)`, T2 sửa `payload.amount` bên ngoài atomic container, rồi T1 CAS dựa trên stamp 4 vẫn thành công. **Stamp không thay đổi**, nên nó không phát hiện mutation của referent. Nếu cập nhật field bình thường xảy ra đồng thời mà thiếu synchronization, còn có nguy cơ **data race** theo JMM.

Một chính sách đúng có thể là:

- Chỉ lưu **immutable state objects** trong AtomicStampedReference; mọi thay đổi tạo object state mới rồi thay cả cặp bằng CAS.
- Hoặc bảo vệ việc sửa mutable referent theo giao thức lock/ownership khác rõ ràng, và đảm bảo cập nhật stamp khi cần.
- Không xuất bản tham chiếu mutable để thread khác tùy ý đổi trong khi thuật toán đang dựa vào tính bất biến của snapshot.

**Tương tự với object graph nhiều cấp:** việc CAS một reference atomic không bảo đảm một thao tác ghi file, cập nhật database hoặc thay ba collection độc lập trở thành một giao dịch thống nhất.

## 12. Stamp overflow, tái sử dụng và giới hạn chống ABA

`stamp` là một `int` Java (32 bit, có dấu). Nếu mỗi lần cập nhật dùng `stamp + 1`, phép cộng có thể **overflow** rồi tiếp tục vòng qua các giá trị cũ. Sau đủ nhiều cập nhật, một cặp `(A, oldStamp)` về mặt lý thuyết **có thể xuất hiện trở lại**.

Ngoài overflow, ABA vẫn có thể xảy ra nếu code:

- Dùng `set(A, oldStamp)` sau khi state thay đổi.
- Reset stamp về 0 khi reload/reinitialize nhưng reader cũ còn tồn tại.
- Có nhiều writer tự chọn newStamp không theo chính sách tăng version.
- Dùng `attemptStamp` hoặc update path khác mà không tuân thủ quy tắc version.
- Áp dụng modulo một tập nhỏ stamp, khiến cặp bị tái sử dụng rất nhanh.

Vì vậy, `AtomicStampedReference` **giảm đáng kể nguy cơ stale CAS theo generation khi version được quản lý đúng**, nhưng không cung cấp bảo đảm “không bao giờ ABA trong mọi hoàn cảnh”.

### Lựa chọn chiến lược version

Tùy yêu cầu:

1. **Chương trình tồn tại không lâu và số mutation bị giới hạn:** một int stamp tăng monotonically trong phạm vi hợp lệ có thể đủ; cần chứng minh không wrap/reuse khi có observer sống lâu.
2. **Không được phép trùng generation theo yêu cầu nghiêm ngặt:** thiết kế version domain lớn hơn, immutable state mang generation/UUID hoặc một cơ chế quản lý epoch phù hợp. `AtomicStampedReference` **chỉ cung cấp int stamp**; không thể giả vờ nó là long/UUID.
3. **Cấu trúc node tái sử dụng:** phối hợp version tagging với cơ chế ownership/reclamation của cấu trúc; versioning đơn lẻ không giải quyết mọi vấn đề của node lifecycle.
4. **Không cần nhận biết generation:** không nên áp stamp chỉ vì nghe nói CAS “có ABA”; tăng phức tạp không mang thêm correctness nếu invariant thực sự chỉ dựa trên current value.

Nói cách khác, trước khi dùng stamped reference, phải xác định **khoảng thời gian một observer có thể giữ snapshot cũ**, tốc độ cập nhật cặp, và khả năng vòng đời/phiên bản quay lại giá trị trước đó.

## 13. AtomicMarkableReference có tương đương không?

Java còn có `AtomicMarkableReference<V>`, quản lý cặp `(reference, boolean mark)`. Một mark boolean rất hữu ích trong các thuật toán dùng đánh dấu logic, ví dụ “node đã bị logically deleted chưa?”. Tuy nhiên, với bài toán phát hiện **bao nhiêu thế hệ đã đi qua**, một bit mark có thể quay 0→1→0 nên không đủ phân biệt mọi ABA.

| Lớp/API | Trạng thái atomic được quản lý | Phù hợp nhất |
|---|---|---|
| `AtomicReference<V>` | Một reference | Chuyển trạng thái chỉ cần kiểm tra current identity |
| `AtomicStampedReference<V>` | Reference + `int stamp` | Cần kiểm tra một version/generation bên cạnh reference |
| `AtomicMarkableReference<V>` | Reference + boolean mark | Cần thêm trạng thái mark, ví dụ logical deletion |
| `AtomicInteger` / `AtomicLong` | Một giá trị số | Counter/flags/các phép số nguyên atomic |
| `synchronized` / `ReentrantLock` | Critical section bảo vệ nhiều field | Cần atomic transaction logic trên nhiều giá trị, không nhất thiết lock-free |

Không có lớp nào mặc nhiên “tốt nhất”. Quyết định dựa trên **semantics của invariant**: cần ngăn writer khác cập nhật đồng thời, hay cần phát hiện lịch sử phiên bản, hay cần đánh dấu logical removal?

## 14. Stamp và tính linearizable

**Linearizability** là tính chất một operation đồng thời có thể được xem như xảy ra tại một điểm nguyên tử nào đó giữa lúc bắt đầu và lúc kết thúc, đồng thời tôn trọng thứ tự thời gian của các operation không chồng lấn.

Với `AtomicStampedReference.compareAndSet`, việc kiểm tra/cập nhật **cặp (reference, stamp)** là một atomic action, giúp programmer xây dựng linearization point cho thao tác cập nhật cặp.

Tuy nhiên:

- Toàn bộ một phương thức nghiệp vụ có thể thực hiện nhiều bước khác ngoài CAS: đọc dữ liệu, validate, ghi side effect, công bố event.
- Một CAS atomic **không tự chứng minh toàn bộ phương thức linearizable**.
- Nếu hai field bên ngoài atomic pair phải chuyển đồng thời, cần giao thức khác bảo vệ cả nhóm hoặc biến chúng thành **một immutable state object** được thay nguyên tử.
- Nếu reader cần thấy generation mới và payload đồng nhất, payload phải được xây dựng/published an toàn và không bị mutate trái phép sau đó.
- Nếu owner/reclamation làm một node không còn hợp lệ trong lúc reader đang dùng, stamp ở head không tự bảo vệ reader khỏi mọi dạng lỗi lifecycle.

Đây là lý do một ví dụ `AtomicStampedReference` chạy đúng vài lần **không phải bằng chứng** một lock-free linked list/stack triển khai hoàn chỉnh đã đúng.

## 15. Java Memory Model liên quan thế nào?

Các lớp atomic của `java.util.concurrent.atomic` định nghĩa memory effects cho những thao tác của chúng. Trên Java 17, đọc thông thường qua `AtomicReference.get()` và các atomic CAS có các hiệu ứng bộ nhớ được API quy định, tương thích với các quy tắc liên quan đến volatile và atomic read-modify-write.

Một snapshot `get(holder)` đủ để lấy cặp reference/stamp nhất quán và một CAS giúp cập nhật cặp nguyên tử, nhưng vẫn phải xét:

- **Publication của object tham chiếu:** nếu object được tạo rồi công bố qua atomic container đúng cách, các ghi chuẩn bị dữ liệu trước publication được phối hợp theo memory semantics thích hợp.
- **Mutability sau publication:** nếu nhiều thread cùng sửa các trường thường bên trong object, cặp atomic không làm những ghi ấy có mutual exclusion hoặc trở thành atomically visible.
- **Không dựa vào `Thread.sleep` làm ordering:** việc scheduler nhường CPU hay chờ một khoảng thời gian không phải quan hệ HB thay thế atomic/lock/latch/join.
- **CAS loop có thể thất bại vì contention:** xử lý retry/failure theo contract; không suy từ một thất bại rằng chắc chắn có ABA—bất kỳ cập nhật cạnh tranh nào cũng có thể làm expected pair sai.

Ở ví dụ thực hành, `Thread.join()` làm thứ tự các bước thử nghiệm được cố định và bảo đảm worker hoàn thành trước khi main tiếp tục. Trong thuật toán concurrent thực, correctness phải đúng **bất kể interleaving nào hợp lệ** theo hợp đồng.

## 16. Đừng nhầm ABA với các vấn đề khác

| Dấu hiệu | Có thể là | Phương pháp phân tích |
|---|---|---|
| CAS thất bại liên tục dưới contention | Cập nhật cạnh tranh / retry starvation | Đo số lần retry, đọc lại expected và new state |
| CAS thành công sau A→B→A nhưng dựa trên snapshot cũ | ABA gây stale decision | Thêm generation/stamp nếu invariant cần |
| CAS thành công nhưng reader thấy field mutable bất thường | Data race trên referent | Kiểm tra safe publication và ownership/lock của payload |
| Hai field không nhất quán dù đã dùng atomic cho từng field | Multi-field invariant bị chia | Gom state thành immutable snapshot hoặc khóa cả transaction |
| Node trong stack bị tái sử dụng với old `next` | ABA và lifecycle/node reuse | Version tagging + algorithm/reclamation audit |
| Consumer nhận event lặp do retry | Side effect đặt trong CAS loop | Tách side effect khỏi retry, idempotency/outbox |
| Version quay lại ban đầu | Wrap-around/tái sử dụng stamp | Xem policy và tuổi thọ snapshot |
| Thứ tự output giữa hai thread thay đổi | Nondeterministic scheduling | Xem yêu cầu nghiệp vụ; không phải ABA nếu không có stale-snapshot false success |

Dùng cùng một từ “race condition” cho mọi lỗi dễ làm chọn sai công cụ. Hãy xác định **điều gì đã được đọc, khi nào giá trị thay đổi, và thao tác cuối xác minh được gì**.

## 17. Thiết kế phiên bản và bất biến: ví dụ tài nguyên logic

Giả sử một trạng thái hệ thống chứa `RecordState(id, status, generation)`. Thread T1 đọc trạng thái “READY thế hệ 7” và chuẩn bị một bước xử lý. Thread T2 có thể hoàn tất thế hệ 7, khởi tạo thế hệ 8, rồi status trở lại READY.

Nếu T1 chỉ CAS enum `READY→RUNNING`, nó không phân biệt hai vòng xử lý. Nếu việc xử lý phải gắn với đúng thế hệ, cần expected **generation 7** được kiểm tra khi nhận quyền.

Có hai cách modeling thông dụng:

**Cách A — AtomicStampedReference:** reference là token/immutable state và stamp là generation, mỗi transition tăng stamp. Consumer dùng `get(holder)` rồi CAS expected pair.

**Cách B — AtomicReference tới immutable object có generation:** tham chiếu trỏ tới một record mới cho mỗi transition. Reader chỉ CAS từ **chính object snapshot cũ** sang object trạng thái mới. Nếu không bao giờ tái sử dụng instance cũ, reference identity sẽ khác ở mỗi generation, nên loại ABA do quay về **cùng reference** trong mô hình đó. Tuy nhiên, phải kiểm soát mọi đường cập nhật và không tái sử dụng object snapshots.

Cách B phù hợp khi nhiều field là một invariant phải cập nhật nguyên tử. Cách A có ý nghĩa khi reference hiện tại có thể quay về cùng identity nhưng phiên bản vẫn cần tách biệt. Không có sự thay thế máy móc một-cho-một mà không xét kiểu dữ liệu và ràng buộc thiết kế.

## 18. Những lỗi triển khai thường gặp

1. **Dùng `getReference()` và `getStamp()` tách biệt rồi tin đó là snapshot.** Có thể có cập nhật ở giữa. Dùng `get(holder)`.
2. **Chỉ tăng stamp khi reference khác.** Nếu thao tác logic thay đổi thế hệ rồi quay về cùng reference, bạn đã tự tái tạo ABA; cần quy ước version cho **mọi mutation có ý nghĩa**.
3. **Reset stamp bằng `set` tùy tiện.** Có thể tái sử dụng cặp cũ mà observer vẫn giữ.
4. **Cho rằng lớp tự tăng stamp.** Mọi `newStamp` do caller cung cấp. `compareAndSet` không tự cộng.
5. **Dùng `equals()` để chọn expected object.** CAS reference so theo `==`; hai object nội dung bằng nhau không nhất thiết cùng reference.
6. **Giữ mutable payload và sửa field trực tiếp.** Stamp không tự phát hiện mutation ngoài container.
7. **Đặt email/network write trong CAS retry.** Retry có thể lặp side effect. Phải có idempotency/transaction riêng.
8. **Cho rằng int stamp duy nhất vô thời hạn.** Overflow hoặc manual reuse có thể tạo lại old pair.
9. **Lạm dụng AtomicStampedReference cho mọi counter.** Nếu invariant chỉ cần tăng nguyên tử, `AtomicInteger.incrementAndGet` đơn giản hơn.
10. **Cho rằng ABA luôn làm kết quả sai.** Nếu quyết định chỉ dựa trên state hiện tại A, ABA có thể không ảnh hưởng. Phải chỉ ra stale assumption bị vi phạm.
11. **Cho rằng CAS của head bảo vệ mọi field node.** Algorithm phải chứng minh cả cấu trúc và lifecycle của node, không chỉ head.
12. **Không xử lý thất bại CAS.** Thất bại có thể là contention bình thường; code cần retry, trả conflict hoặc chiến lược khác.
13. **Tạo desired state từ snapshot cũ rồi retry CAS với expected mới mà không tính lại.** Kết quả mới có thể dựa trên một invariant đã lỗi thời.
14. **Tưởng stamp là timestamp từ đồng hồ.** Nó là int do caller quản lý; không tự có quan hệ với thời gian thực.
15. **Cho rằng giải quyết ABA tức có lock-free, wait-free và fairness.** Đây là thuộc tính riêng của toàn thuật toán.
16. **Suy từ một test pass rằng không thể ABA nữa.** Phải phân tích mọi đường thay đổi stamp và giới hạn vòng đời/version.

## 19. Cách thử nghiệm ABA có tính tái hiện

Một chiến lược thử nghiệm hiệu quả hơn việc stress ngẫu nhiên ngay từ đầu:

1. **Xác định invariant:** ví dụ “nếu state đã trải qua một thế hệ khác từ lúc tôi đọc thì không được commit dựa trên snapshot cũ”.
2. **Đặt snapshot đầu tiên:** thread T1 đọc A và (nếu có) version 0.
3. **Tạo lịch cưỡng bức:** dùng `CountDownLatch`, `CyclicBarrier` hoặc `Thread.join()` để T2 hoàn thành A→B→A trong khi T1 vẫn giữ expected cũ.
4. **Thử CAS của T1:** `AtomicReference` sẽ chấp nhận nếu identity là A; stamped CAS với version 0 sẽ thất bại nếu version hiện tại là 2.
5. **Đọc lại và chứng minh retry:** T1 lấy cặp mới rồi tính lại desired; nếu không còn cạnh tranh, CAS có thể thành công.
6. **Kiểm tra payload/structure invariants:** không chỉ assert true/false của CAS; nếu algorithm là stack, kiểm tra không mất node, không tạo cycle, không truy cập node không còn hợp lệ.
7. **Thử đường sai:** cố ý reset stamp, bỏ tăng version, mutate referent nội bộ để thấy những điều `AtomicStampedReference` không bảo đảm.
8. **Thử stress/real contention:** nhiều thread, nhiều iteration, dữ liệu ngẫu nhiên có kiểm soát và assertions. Thất bại là bằng chứng bug; nhiều lần pass không phải chứng minh formal correctness.

Trong demo runnable, `Thread.join()` là cách đơn giản để buộc T2 hoàn thành trước T1 CAS. Trong một bài test thuật toán lock-free thật, một hoặc nhiều barrier/latch giúp kiểm soát checkpoint **mà không cần dùng sleep**.

### Về benchmark

`AtomicStampedReference` có thể phát sinh chi phí quản lý cặp phiên bản, contention và allocation tùy triển khai. Đừng khẳng định nó nhanh hơn/chậm hơn mọi CAS thường mà không đo đúng workload/JDK. Benchmark cần so sánh các phiên bản **đều đúng về logic**; một thuật toán bỏ stamp có thể “nhanh hơn” nhưng sai trong lịch ABA quan trọng.

Nếu đo contention và latency, cân nhắc JMH cho microbenchmark Java. Tránh benchmark chỉ một lần bằng `System.nanoTime()` rồi xem chênh lệch nhỏ là kết luận chắc chắn.

## 20. Khi nào nên và không nên dùng AtomicStampedReference?

**Nên cân nhắc khi:**

- Logic yêu cầu phát hiện **đã có transition từ lúc snapshot**, kể cả current reference quay về object ban đầu.
- Đã có thiết kế optimistic CAS với một reference có thể được **tái sử dụng**.
- Có chính sách stamp rõ ràng, không tái sử dụng trong lifetime observer có liên quan.
- Muốn giữ reference + version là một atomic pair mà không đặt lock cho phần cập nhật đó.
- Có khả năng kiểm chứng mọi read/write path đi qua atomic container, không mutate referent trái quy tắc.

**Không mặc định dùng khi:**

- Chỉ cần `counter++` hoặc phép update một giá trị độc lập: `AtomicInteger`/`AtomicLong` hợp hơn.
- Cần bảo vệ invariant của nhiều mutable field không thể gói vào một immutable snapshot: `synchronized`/`ReentrantLock` thường rõ hơn.
- Dữ liệu đã được thiết kế immutable và mỗi transition tạo **instance state mới duy nhất**; `AtomicReference<ImmutableState>` có thể đủ.
- Có thuật toán collection sẵn có như `ConcurrentLinkedQueue`, `ConcurrentHashMap`, `BlockingQueue`: ưu tiên primitive được kiểm chứng thay vì tự triển khai cấu trúc lock-free.
- Cần “version không bao giờ trùng” trong vòng đời cực dài mà `int` không đáp ứng; phải chọn version domain/architecture khác.
- Muốn giải quyết serialization xuyên database/process: atomic Java chỉ bảo vệ state trong JVM phù hợp, không tự thành distributed transaction.

## 21. Câu hỏi tự kiểm tra và đáp án

**Câu 1.** T1 đọc reference A. T2 CAS A→B→A và T1 tiếp tục CAS A→C. Vì sao CAS thường có thể trả true?  
**Đáp án:** CAS thường chỉ so reference hiện tại với expected A. Khi current đã trở lại chính object A, nó không có thông tin về B đã tồn tại ở giữa.

**Câu 2.** Chỉ cần phát hiện A→B→A là đủ kết luận có bug?  
**Đáp án:** Không. ABA chỉ gây lỗi nếu T1 có giả định rằng state/structure chưa thay đổi kể từ snapshot và giả định ấy là yêu cầu correctness.

**Câu 3.** Tại sao `AtomicStampedReference` ngăn ví dụ với `(A,0)→(B,1)→(A,2)`?  
**Đáp án:** T1 kỳ vọng cả reference A **và** stamp 0; current stamp 2 nên CAS cũ thất bại.

**Câu 4.** `AtomicStampedReference` có tự tăng stamp khi gọi `compareAndSet` không?  
**Đáp án:** Không. Caller truyền newStamp. Phải quy định mọi đường mutation có ý nghĩa đều cập nhật version.

**Câu 5.** Dùng `getReference()` rồi `getStamp()` có chắc là cùng snapshot không?  
**Đáp án:** Không; có thể thread khác cập nhật giữa hai call. Dùng `get(int[] stampHolder)`.

**Câu 6.** Hai instance `new String("A")` có `equals` nhau; CAS reference có coi là cùng expected không?  
**Đáp án:** Không. Reference CAS dùng identity `==`, không dùng `equals()`.

**Câu 7.** Referent `Payload` bị sửa `payload.value` nhưng reference và stamp không đổi. Stamped CAS có tự phát hiện không?  
**Đáp án:** Không. Nó chỉ kiểm tra cặp reference/stamp. Mutable fields phải được bảo vệ bằng state design/ownership/lock khác.

**Câu 8.** Vì sao `int stamp` có thể không đủ trong hệ thống dài hạn?  
**Đáp án:** Nó có số giá trị hữu hạn và có thể overflow/wrap, hoặc bị code chủ động reset, cho phép cặp cũ xuất hiện lại.

**Câu 9.** Lỗi của stale `next` trong lock-free stack có được giải quyết hoàn toàn chỉ bằng AtomicStampedReference?  
**Đáp án:** Không thể khẳng định như vậy. Stamp giúp ngăn CAS dựa trên version head cũ, nhưng còn cần kiểm chứng toàn bộ thuật toán, node reuse và memory reclamation/lifecycle.

**Câu 10.** Có thể gọi side effect bên trong vòng lặp CAS retry không?  
**Đáp án:** Không nên với side effect không thể lặp. CAS có thể fail nhiều lần nên tác động có thể bị thực hiện lặp, và CAS không tạo transaction với external systems.

**Câu 11.** Nếu CAS với stamp cũ thất bại, sửa bằng việc lấy latest stamp rồi CAS ngay với desired tính từ snapshot cũ có đúng không?  
**Đáp án:** Không nhất thiết. Phải đọc lại **cả reference/stamp**, kiểm tra invariant và **tính lại desired** theo snapshot mới trước khi retry.

**Câu 12.** `AtomicMarkableReference` và `AtomicStampedReference` có cùng công dụng không?  
**Đáp án:** Không. Markable dùng boolean mark, phù hợp đánh dấu logic; stamped dùng int version, hữu ích để phân biệt các thế hệ thay đổi.

## 22. Tài liệu tham khảo

- [Java SE 17 — AtomicStampedReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicStampedReference.html): constructor, `get(int[])`, `compareAndSet`, `set`, `attemptStamp`.
- [Java SE 17 — AtomicReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): `get`, `set`, `compareAndSet`.
- [Java SE 17 — AtomicMarkableReference](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicMarkableReference.html): reference kết hợp boolean mark.
- [Java SE 17 — java.util.concurrent.atomic](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/package-summary.html): giới thiệu các atomic classes và memory effects.
- [Java Language Specification Java SE 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): data race, happens-before và memory ordering.
- [Java SE 17 — Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `start`, `join` và các quan hệ completion.

**Tóm tắt cuối:** **ABA = current trở về A sau khi đã thay đổi ở giữa**. CAS thường kiểm tra current identity nên có thể cho stale update thành công. `AtomicStampedReference` bổ sung **generation/stamp** để CAS kiểm tra một **cặp (reference, version)**. Nó có hiệu quả khi **mọi mutation quan trọng tăng version, version không bị tái dùng trong khoảng có observer, referent được quản lý an toàn và thuật toán được chứng minh trọn vẹn**.