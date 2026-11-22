# Write barrier, card table và remembered set khi theo dõi tham chiếu

## 1. Vấn đề cốt lõi

Một Java heap chứa hàng triệu đối tượng và các tham chiếu giữa chúng. Khi ứng dụng đang chạy, những phép gán như **holder.child = newChild** liên tục thay đổi đồ thị đối tượng. Nếu bộ gom rác (GC) chỉ thu gom một phần heap hoặc đánh dấu đồng thời với các thread ứng dụng, nó cần biết **các cạnh tham chiếu nào có thể đã thay đổi** mà không buộc phải quét toàn bộ heap sau mỗi phép gán.

Ba khái niệm giải quyết phần lớn câu chuyện trong các generational/region-based tracing collectors:

- **Write barrier:** phần logic nội bộ GC được thực hiện quanh thao tác ghi tham chiếu (trước hoặc sau ghi), giúp duy trì thông tin về biến đổi đồ thị heap.
- **Card table:** cấu trúc metadata chia các địa chỉ heap thành những **card** nhỏ; khi ghi vào một vị trí có tham chiếu đáng quan tâm, collector có thể đánh dấu card tương ứng là **dirty** để quét lại.
- **Remembered set (RSet):** cấu trúc tóm tắt những **vị trí nguồn ở ngoài vùng đang thu gom** có thể tham chiếu **vào vùng đó**; giúp thu gom vùng riêng mà không scan toàn bộ heap còn lại.

Với HotSpot **G1 Garbage Collector**, còn có hai nhiệm vụ barrier nên phân biệt rõ:

1. **Post-write barrier** phục vụ **tracking các tham chiếu chéo region**, đóng góp vào card/remembered-set maintenance.
2. **Pre-write barrier** phục vụ **Snapshot-At-The-Beginning (SATB)** trong concurrent marking, chủ yếu xử lý **tham chiếu cũ sắp bị ghi đè**.

Hai barrier này cùng liên quan write operations nhưng **không phải một thuật toán, không ghi cùng dữ liệu và không tồn tại chỉ nhằm tracking old-to-young**.

Sau bài, bạn có thể đọc một đồ thị references, dự đoán card nào phải được xét, giải thích ý nghĩa một inbound RSet, phân biệt SATB pre-/G1 post-barrier, hiểu chi phí đồng bộ hóa với mutator, dùng GC logs đúng cách và tránh kết luận sai về tính reachability từ một dirty card.

Bài sử dụng **HotSpot G1 trên JDK 17** làm ví dụ cụ thể và phân biệt rõ **nguyên lý tracing GC** với **chi tiết collector implementation**. JVMS **không bắt buộc** một JVM sử dụng card table, RSet hay chính các barriers của G1.

## 2. Nền tảng: GC roots, object graph và thu gom từng phần

Trong mô hình object graph:

- Một **object/array** là một đỉnh.
- Một **reference field/array element** tạo một cạnh có hướng.
- **GC roots** là các nguồn tham chiếu đang live.
- Một object còn **strongly reachable** nếu có đường tham chiếu mạnh phù hợp từ roots đến nó.

Ví dụ:

~~~text
Root --> Old object A --> Young object Y
             |
             +----------> Old object B

Root --> Young object Z
~~~

Nếu thu gom toàn heap, collector có thể bắt đầu tại tất cả roots rồi duyệt các cạnh theo thiết kế. Nhưng **minor/young collection** chỉ muốn xử lý young objects. Vấn đề: **Y có thể sống vì old object A đang trỏ tới nó**. Quét mỗi young region và thread roots mà bỏ qua old-to-young edges sẽ có nguy cơ xử lý Y như rác khi thực ra nó còn reachable.

### 2.1. Tại sao không quét toàn bộ old generation mỗi lần?

Giả sử old heap có 12 GiB nhưng young generation chỉ có vài trăm MiB. Quét lại tất cả old objects ở mọi young GC có thể rất đắt, đi ngược mục tiêu thu gom nhanh những objects ngắn hạn.

GC cần một **nguồn thông tin tóm tắt** cho biết: “Những vùng/vị trí ở ngoài collection set nào có thể chứa references đi vào collection set?”

Đây là lý do xuất hiện **remembered sets và card marking**. Chúng có thể cho phép một collector xử lý một phần heap trong khi vẫn xem xét **các cạnh từ bên ngoài phần được thu gom**.

### 2.2. G1 không chỉ có hai khoảng young/old liên tục

G1 phân heap thành **regions** (các đoạn địa chỉ heap có kích thước đều trong một cấu hình cụ thể). Tại mỗi thời điểm, một region có thể giữ Eden, Survivor, Old hoặc dữ liệu đặc biệt như humongous objects theo cơ chế collector.

~~~text
G1 heap (sơ đồ logic):
 +--------+--------+--------+--------+--------+--------+
 | Eden A | Old B  | Old C  | Surv D | Eden E | Old F  |
 +--------+--------+--------+--------+--------+--------+
           |         |                  ^
           +----------------------------+
                     |
           Có thể có cross-region refs
~~~

G1 có thể thu gom **collection set (CSet)** gồm những regions được chọn. Trong một young GC, phần CSet thường chứa young regions; một mixed collection còn có thể gồm một số old regions. Vì vậy **tracking cross-region references** là mục tiêu rộng hơn việc chỉ tracking old-to-young.

## 3. Write barrier là gì?

**Write barrier** trong GC là đoạn công việc mà runtime/compiler thêm vào đường thực hiện **một số thao tác ghi tham chiếu**. Nó có thể kiểm tra old/new reference, địa chỉ ô nhớ được ghi, trạng thái marking, region membership và cập nhật metadata/queues.

Biểu thức Java:

~~~java
owner.child = newChild;
~~~

về logic:

~~~text
Thông tin trước ghi: oldValue = owner.child
                  |
       [Có thể có pre-write barrier]
                  |
       STORE owner.child = newChild
                  |
       [Có thể có post-write barrier]
                  |
             Tiếp tục chạy
~~~

Đây là mô hình hành vi, **không** phải cam kết mọi object field store luôn sinh hai hàm gọi Java độc lập. Barriers thường được JIT/interpreter/VM intrinsics tạo ở mức thấp; compiler có thể tối ưu khi biết store không cần một số bookkeeping.

### 3.1. Pre-write vs post-write

| Đặc điểm | Pre-write barrier | Post-write barrier |
| --- | --- | --- |
| Mốc khái niệm | Trước khi overwrite một reference slot | Sau khi store reference mới |
| Dữ liệu quan tâm | Thường là **old referent** bị thay thế | Thường là **slot/source location** vừa đổi và/hoặc new referent |
| Ví dụ trong G1 | Ghi nhận old value cho **SATB concurrent marking** | Card marking/dirty-card queue phục vụ cross-region RSet |
| Tại sao cần? | Tránh làm mất cạnh thuộc snapshot đang được đánh dấu | Đừng bỏ sót nguồn reference mới đi vào collection region |
| Có cần mọi lúc? | Phụ thuộc marking phase và kiểm tra khác | Phụ thuộc kind of store, source/target regions và runtime conditions |

**Không có định nghĩa toàn cầu** rằng pre-write luôn dùng cho SATB hay post-write luôn dùng cho remembered set trong mọi collector. Đây là sự phân vai **điển hình ở G1 HotSpot JDK 17**. Các collectors khác dùng barriers khác, thậm chí đọc tham chiếu cũng có **load/read barriers**.

### 3.2. Write barrier khác memory barrier của Java Memory Model

GC write barrier **không đồng nghĩa** CPU memory fence, volatile semantics hoặc monitor synchronization.

- **Write barrier GC:** giữ đúng thông tin phục vụ collector.
- **Memory barrier/fence/JMM ordering:** phục vụ visibility/ordering/happens-before giữa threads.
- **Card table:** metadata GC không phải một cách publish đối tượng đến threads khác.

Một **owner.child = x** bình thường có thể làm thay đổi card metadata nhưng **không vì thế** tạo ra happens-before giữa các threads. Nếu cần thread safety, vẫn sử dụng volatile, locks, atomics hoặc synchronization phù hợp.

## 4. Card table: bản đồ đánh dấu các khối nhỏ của heap

Một **card** là một phần nhỏ của vùng địa chỉ heap được chia đều theo cơ chế card-table của collector. Với G1 HotSpot, kích thước card điển hình được tài liệu mô tả là **512 byte**, nhưng nên xem đây là **chi tiết phiên bản/implementation**, không phải hằng số của Java language.

Ví dụ giả định:

~~~text
Heap base = 0
Card size = 512 bytes

  Card 0: [    0,   511]
  Card 1: [  512,  1023]
  Card 2: [ 1024,  1535]
  Card 3: [ 1536,  2047]
  ...
~~~

Một mô hình ánh xạ đơn giản:

~~~text
cardIndex = floor((slotAddress - heapBase) / cardSize)
~~~

Nếu một reference field nằm tại địa chỉ offset **760**, thì:

~~~text
floor(760 / 512) = 1
~~~

Collector quan tâm đến **card 1** để có thể quét lại các reference slots trong khoảng địa chỉ liên quan.

### 4.1. Card table lưu cái gì?

Một mô hình học tập đơn giản:

~~~text
Heap:
  card 0  card 1  card 2  card 3
    |       |       |       |
    v       v       v       v
   [0..] [.. ]  [.. ]  [.. ]

Card-table metadata:
   CLEAN  DIRTY   CLEAN  CLEAN
~~~

Trong implementations thật, một card có thể có nhiều trạng thái/bits hoặc cơ chế buffers khác nhau; không nhất thiết chỉ là một Java boolean.

**Dirty** chỉ là “nên xem xét lại vùng này”; nó **không có nghĩa**:

- Có chính xác một reference đã thay đổi.
- Target object còn sống hoặc vừa được tạo.
- Card chắc chắn chứa old-to-young reference ở thời điểm GC.
- Card nằm trong collection set.
- Mọi bytes trong card đều là Java references.
- Một dirty event tương ứng một bản ghi RSet mới.

Một card chứa nhiều objects/reference slots; ghi cùng card hàng trăm lần vẫn có thể được coalesced thành ít bookkeeping entries.

### 4.2. Vì sao granularity là card thay vì từng reference slot?

Nếu mỗi byte/slot store phải cập nhật một index chính xác tới từng object reference, metadata và synchronization có thể rất đắt. Đánh dấu **vùng nhỏ** là sự đánh đổi:

- **Ưu:** cập nhật tại mutator rẻ, metadata nhỏ, batch được nhiều writes.
- **Nhược:** collector có thể phải scan một card dù chỉ một reference field thay đổi, tức có **false positives/coarse precision**.

Đây là một ví dụ tối ưu **write-time overhead vs scan-time overhead**, không phải “mất thông tin dẫn tới thu hồi nhầm”. Collector phải giữ đủ độ đúng để không bỏ sót live references.

## 5. Remembered set: những nguồn nào tham chiếu vào một vùng?

**Remembered set (RSet)** là metadata giúp collector tìm references từ **ngoài vùng cần thu gom** vào bên trong. Ở mô hình G1 JDK 17, cách diễn giải thuận tiện là **inbound RSet** cho target region: một tập các source locations/cards có thể chứa pointers vào target.

Ví dụ:

~~~text
             outside collection set
  Old Region R1                  Old Region R2
  +-------------------+          +-------------------+
  | Object A          |          | Object B          |
  | field x ----------+--------+ | field y ----------+-------+
  +-------------------+        | +-------------------+       |
                               |                             |
                               v                             v
                        Young Region R3 (CSet)
                        +----------------------+
                        | Object P   Object Q  |
                        +----------------------+

Inbound RSet for R3 (minh họa):
    possible source cards in R1, R2
~~~

Khi thu gom R3, collector không cần scan nguyên R1 và R2; nó có thể xem những source cards được chỉ định và kiểm tra references thật.

### 5.1. RSet không phải danh sách tất cả objects đang sống

RSet thường chứa **các vị trí ứng viên** — có thể biểu diễn bằng cards, ranges hoặc các cấu trúc nén theo implementation. Khi quét:

- Một candidate card có thể chứa pointer vào R3.
- Một candidate card có thể đã không còn pointer liên quan vì reference slot bị sửa/null.
- Một card có thể chứa nhiều pointers thuộc nhiều objects.
- Một pointer thật vẫn phải được kiểm tra xem target thuộc collection set và phải được xử lý ra sao.

Do đó, RSet được dùng như **nguồn để tìm incoming edges**, không phải một “đồ thị complete object identity chính xác từng byte” cũng không phải reachability proof cho mọi object.

### 5.2. RSet là inbound, không phải outbound

Với cạnh **A trong R1 → B trong R3**:

- Đây là **outbound edge** khi đứng ở R1.
- Nhưng là **inbound edge** khi đứng ở R3.
- RSet của **target R3** ghi nhận **nơi nguồn từ R1 có thể tham chiếu vào R3**.

Nếu nói “RSet của R1 ghi các references R1 trỏ đi nơi khác”, đó không phải cách diễn giải chuẩn của **per-target inbound RSet** đang bàn. Một collector khác có thể có data structures khác, nên luôn nêu rõ hướng RSet.

### 5.3. Old-to-young là trường hợp phổ biến, không phải duy nhất

Với generational GC:

~~~text
Old O ----> Young Y
~~~

Đây là đường rất quan trọng trong young GC. Nhưng G1 còn tracking các cạnh **old region A → old region B** khi cần thu gom B trong mixed collection, và có những cross-region edges giữa các young regions.

Không nên rút gọn G1 remembered set thành “một list tất cả old objects trỏ young objects”. Nó là cấu trúc theo **regions/locations** với chính sách duy trì phụ thuộc collector.

## 6. Pipeline G1: write → dirty card → refinement → RSet

Ví dụ giả định một reference field trong source region R1 được cập nhật để trỏ vào target region R3:

~~~text
(1) Mutator thread:
    A.child = P       A thuộc R1, P thuộc R3
          |
          v
(2) G1 post-write barrier (điều kiện phù hợp)
    xác định reference/source slot đáng quan tâm
    đánh dấu source card là dirty
    có thể đưa card vào dirty-card queue
          |
          v
(3) Concurrent refinement / GC pause processing
    lấy dirty cards đã được ghi nhận
    scan references thích hợp trong card
    xác định actual cross-region targets
          |
          v
(4) Update remembered set metadata
    Inbound RSet của R3 ghi nhận source location/card
          |
          v
(5) Khi thu gom collection set gồm R3:
    scan incoming candidates từ RSet
    kiểm tra references thật và xử lý moved objects
~~~

Thành phần thực tế có thêm chính sách lược bớt, buffering, card states, collection-set handling, queue thresholds, forwarding pointers, remembered-set coarsening và các pha khác. Đây là **pipeline để hiểu trách nhiệm**, không phải đồ thị flow bắt buộc nguyên dạng ở mọi G1 build.

### 6.1. Vì sao không cập nhật RSet ngay trong mỗi assignment?

Lý do chính là giảm overhead của mutator:

- Có thể nhiều field writes cùng card.
- Một card có thể đổi target nhiều lần trước khi collector scan.
- Mutator có thể chỉ cần ghi metadata/queue; thread khác refinement theo batch.
- Cập nhật concurrent RSet trực tiếp từng reference có thể cần synchronization, allocation hoặc random memory accesses tốn kém.

G1 sử dụng **dirty card buffers/queues** và **concurrent refinement** để chuyển bớt công việc ra khỏi đường nóng của ứng dụng. Nhưng nếu backlog lớn, GC pause có thể phải xử lý các cập nhật RSet còn pending trước khi scan candidates.

### 6.2. Điều gì nếu write thay reference rồi lại xóa trước refinement?

~~~text
t0: A.child = null
t1: A.child = P (P in R3)     -> card dirty
t2: A.child = null            -> card lại có thể được ghi nhận
t3: refinement scan current slot
    A.child == null
~~~

Nếu chỉ xét slot này và không còn pointer khác vào R3 trong card, collector có thể loại/không bổ sung candidate tương ứng theo chính sách implementation. **Dirty card không chứng minh giá trị reference vừa được ghi vẫn còn hiện hữu**.

Đó cũng là lý do RSet processing thường phải đối chiếu **current references** khi phù hợp, không chỉ tin một sự kiện assignment lịch sử.

## 7. G1 pre-write barrier: SATB và old reference

G1 còn làm concurrent marking để xác định live objects trong old-generation areas phục vụ lựa chọn regions cho mixed collections. Đánh dấu diễn ra trong khi mutator có thể thay đổi đồ thị tham chiếu.

**SATB — Snapshot-At-The-Beginning** dùng khái niệm “giữ các đối tượng có trong snapshot ban đầu” theo thuật toán. Một quan hệ đang tồn tại vào thời điểm bắt đầu mark có thể bị mutator xóa trước khi marker thread duyệt cạnh đó.

Ví dụ:

~~~text
Khi bắt đầu marking (snapshot logic):
  Root ---> A ---> X

Mutator sắp ghi:
  A.child = Y

Trước STORE:
  oldValue = X
  G1 pre-barrier có thể enqueue X (nếu SATB marking active)

Sau STORE:
  A.child = Y
~~~

Nếu X chỉ còn được dẫn đến qua cạnh cũ **A.child**, việc xóa cạnh giữa lúc mark có thể làm marker không thấy X qua đường thông thường. Enqueue old reference trong **SATB buffer** giúp duy trì bất biến snapshot của concurrent mark, tránh bỏ sót một object cần được xem là live theo thuật toán.

Điểm cần nhớ:

- **Pre-barrier quan tâm old value** trước khi bị ghi đè, **không phải chỉ new value**.
- Thường chỉ active khi SATB concurrent marking đang cần; có fast-path guards.
- Một số writes có thể được compiler/VM tối ưu và không sinh thực hiện pre-barrier riêng nếu chứng minh an toàn.
- Objects được giữ live do snapshot dù sau đó không còn đường hiện thời có thể tạo **floating garbage**, được thu hồi ở các chu kỳ sau.

### 7.1. SATB pre-barrier có dùng card table để ghi old value không?

Không nên đồng nhất. SATB pre-barrier G1 thường đưa **old referent** vào một **SATB marking queue/buffer** khi điều kiện phù hợp. Trong khi đó, post-write barrier phục vụ **card/RSet tracking**. Cả hai có thể liên quan đến cùng một assignment nhưng **dữ liệu và invariant khác nhau**.

### 7.2. Nguy cơ nếu không xử lý cạnh bị xóa trong concurrent mark

Sơ đồ ba màu:

- **White:** chưa mark/khám phá.
- **Grey:** đã phát hiện nhưng chưa quét hết edges.
- **Black:** đã xử lý trong mô hình marking.

Nếu mutator xóa một đường dẫn tới object trắng thuộc snapshot trước khi marker phát hiện, có thể cần SATB bookkeeping để tránh sai lệch. Đây chỉ là trực giác; thuật toán thực có xử lý allocations sau snapshot, barriers, termination checks và GC-specific invariants.

Không suy rằng “X đã chuyển thành unreachable nên được thu hồi ngay trong cùng mark cycle” — SATB có thể cố ý giữ X qua chu kỳ hiện tại để bảo toàn safety.

## 8. G1 post-write barrier: card marking cho cross-region pointers

Ngược lại, post-write barrier tập trung vào **reference mới được lưu** và **địa chỉ source slot** vừa thay đổi. Khi đó collector cần biết có thể xuất hiện một edge từ region này tới region khác.

Sơ đồ:

~~~text
Trước:
    A thuộc R1
    A.child = null

Ghi:
    A.child = P;  // P thuộc R3

Sau:
    R1 --(reference slot của A)--> R3
                   |
                   v
         Dirty source card (ứng viên)
                   |
                   v
         Refine cập nhật inbound RSet R3
~~~

Với G1, post-barrier có thể dùng những điều kiện lọc như null references, nguồn/đích cùng region, card state, vùng thuộc young generation và những optimization khác. **Không phải mọi lần gán một Java reference đều dirty card**.

### 8.1. Pseudo-code dạy học của hai barriers

~~~text
function storeReference(slot, newReferent):
    oldReferent = slot.currentReferent

    // Pre-write: khi SATB marking active và old value liên quan
    if satbMarkingActive and oldReferent != null:
        enqueueSATBCandidate(oldReferent)

    // Java-level store
    slot.currentReferent = newReferent

    // Post-write: khi chính sách cross-region tracking cần
    if newReferent != null and crossesRelevantRegionBoundary(slot, newReferent):
        dirtyCard(slot.address)
        enqueueCardForRefinementIfNeeded()
~~~

**Đây là pseudo-code về trách nhiệm**, không phải HotSpot C++ chính xác. Các đường ghi null, copy arrays, initialization barriers, concurrent races, card-queue coalescing, oop compression, GC barriers và compiler optimizations khiến implementation thực phức tạp hơn.

Quan trọng hơn, **đánh dấu card và bổ sung inbound RSet không nhất thiết cùng xảy ra ngay trong mutator write**.

## 9. G1 collection set và inbound scanning

G1 chọn một tập regions để thu gom, gọi là **collection set/CSet**. Với references từ ngoài CSet trỏ vào objects trong CSet, collector cần tìm và cập nhật chúng nếu live objects bị di chuyển.

~~~text
Outside CSet:                         Inside CSet:
  R1 [A.child -----------]-----> R3 [P]
  R2 [B.entry ----------]-----> R3 [Q]

R3 inbound RSet (candidates):
  Card chứa A.child trong R1
  Card chứa B.entry trong R2
~~~

Trong thời gian GC pause, collector:

1. Lấy các roots và incoming candidates vào CSet.
2. Duyệt/kiểm tra actual references thích hợp.
3. Di chuyển live objects nếu collector evacuation cho phép.
4. Cập nhật các tham chiếu trỏ tới vị trí cũ theo cơ chế GC.
5. Xử lý metadata/remembered-set trạng thái phù hợp cho chu kỳ tiếp theo.

**RSet không thay thế toàn bộ GC roots.** Các roots như thread stacks, static/JNI handles và GC-specific sources vẫn cần được xử lý. RSet bổ sung đường **heap-to-heap references từ ngoài CSet**.

### 9.1. Không được chỉ quét target region

Nếu R3 chỉ chứa Y còn A ở old region R1 trỏ tới Y, muốn giữ Y sống qua evacuation phải biết đường từ A. Việc “Y đang nằm trong young” không cho biết Y live; RSet cung cấp cách tìm các external incoming edges để GC xử lý đúng.

### 9.2. Một RSet candidate có thể stale hoặc coarse

Giả sử RSet của R3 nói card K ở R1 “có thể chứa pointer vào R3”. Sau nhiều updates, nó có thể không còn pointer ấy. Scan sẽ kiểm tra và bỏ qua không cần thiết. False positives làm tăng scan cost nhưng **không gây nhầm đối tượng chết thành object không an toàn để thu hồi** trong mô hình chính xác của collector.

Đối lập, **false negative nguy hiểm**: một pointer thật từ ngoài CSet vào CSet bị bỏ sót có thể làm collector mất một đường giữ sống hoặc không cập nhật reference sau relocation. Barrier/queue synchronization được thiết kế để tránh điều đó.

## 10. Ví dụ Java 17+: mô phỏng card table và inbound RSet

Đây là **một chương trình Java chạy được nhưng chỉ mô phỏng**, không can thiệp G1 thật. Nó cố ý đánh dấu card bất cứ khi nào reference slot được ghi, rồi quét những slots hiện có để cập nhật candidate inbound cards. Nhờ vậy có thể thấy dirty cards không phải bản ghi chính xác của giá trị cuối cùng.

Tạo file **CardRememberedSetModel.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class CardRememberedSetModel {
    private static final int CARD_BYTES = 512;

    static final class RefSlot {
        final int heapOffset;
        final int sourceRegion;
        int targetRegion; // -1 đại diện null

        RefSlot(int heapOffset, int sourceRegion) {
            this.heapOffset = heapOffset;
            this.sourceRegion = sourceRegion;
            this.targetRegion = -1;
        }
    }

    private static final List<RefSlot> SLOTS = new ArrayList<>();
    private static final Set<Integer> DIRTY = new TreeSet<>();
    private static final Map<Integer, Set<Integer>> INBOUND =
            new TreeMap<>();

    static void write(RefSlot slot, int newTargetRegion) {
        slot.targetRegion = newTargetRegion;
        DIRTY.add(slot.heapOffset / CARD_BYTES);
    }

    static void refine() {
        for (int card : DIRTY) {
            // Bỏ entries cũ của card trong model.
            for (Set<Integer> sourceCards : INBOUND.values()) {
                sourceCards.remove(card);
            }

            // Scan các current reference slots thuộc card.
            for (RefSlot slot : SLOTS) {
                int slotCard = slot.heapOffset / CARD_BYTES;
                if (slotCard == card
                        && slot.targetRegion >= 0
                        && slot.sourceRegion != slot.targetRegion) {
                    INBOUND.computeIfAbsent(
                            slot.targetRegion, key -> new TreeSet<>()
                    ).add(card);
                }
            }
        }
        DIRTY.clear();
    }

    static Set<Integer> inbound(int region) {
        return INBOUND.getOrDefault(region, Set.of());
    }

    public static void main(String[] args) {
        RefSlot first = new RefSlot(600, 0);
        RefSlot second = new RefSlot(620, 0);
        SLOTS.add(first);
        SLOTS.add(second);

        write(first, 2);
        write(second, 2);
        System.out.println("dirty=" + DIRTY);

        refine();
        System.out.println("inbound2=" + inbound(2));

        write(first, -1);
        refine();
        System.out.println("afterOneNull=" + inbound(2));

        write(second, -1);
        refine();
        System.out.println("afterBothNull=" + inbound(2));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 CardRememberedSetModel.java
java CardRememberedSetModel
~~~

**Stdout cố định:**

~~~text
dirty=[1]
inbound2=[1]
afterOneNull=[1]
afterBothNull=[]
~~~

**Lý do:**

1. Heap offsets 600 và 620 cùng nằm trong **card index = 1** vì 512 ≤ offset ≤ 1023.
2. Hai writes vào target region 2 khiến model đặt duy nhất **dirty card 1**.
3. Refine scan thấy hai refs từ source region 0 sang target region 2; inbound RSet target 2 có candidate **card 1**.
4. Xóa first reference nhưng second còn, nên inbound card 1 vẫn tồn tại.
5. Xóa second rồi refine khiến current card không còn refs sang region 2, nên tập inbound thành [].

**Khác biệt với G1 thực:**

- Model lưu **source/target region IDs** do Java code chỉ định, không đo region membership thực.
- Model dirty mọi write và sửa RSet ngay khi refine; G1 có guards/queues/coarsening, race protocols và handling khác.
- Model xóa stale candidates bằng cách scan card đầy đủ; G1 không có nghĩa giữ chính cấu trúc TreeMap hoặc xóa mọi entries theo một thuật toán Java như thế.
- Model không có GC roots, object liveness, evacuation, SATB, concurrent refinement hay actual heap addresses.

Vì vậy chương trình giải thích **logic metadata**, chứ không phải API điều khiển G1.

## 11. Ví dụ Java 17+: mô phỏng SATB pre-barrier

Tạo file **SATBPreWriteModel.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SATBPreWriteModel {
    static final class RefSlot {
        String value;

        RefSlot(String value) {
            this.value = value;
        }
    }

    static final List<String> SATB_QUEUE = new ArrayList<>();
    static boolean marking = true;

    static void overwrite(RefSlot slot, String newValue) {
        String oldValue = slot.value;

        // Pre-write logging: old reference, trước store.
        if (marking && oldValue != null) {
            SATB_QUEUE.add(oldValue);
        }

        slot.value = newValue;
    }

    public static void main(String[] args) {
        RefSlot ref = new RefSlot("A");
        overwrite(ref, "B");
        overwrite(ref, null);

        System.out.println("oldCandidates=" + SATB_QUEUE);
        System.out.println("current=" + ref.value);

        marking = false;
        overwrite(ref, "C");
        System.out.println("afterMarking=" + SATB_QUEUE);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 -encoding UTF-8 SATBPreWriteModel.java
java SATBPreWriteModel
~~~

**Stdout chính xác:**

~~~text
oldCandidates=[A, B]
current=null
afterMarking=[A, B]
~~~

Diễn giải:

- Ghi A→B khi marking đang active có thể ghi nhận **A**, là tham chiếu cũ.
- Ghi B→null có thể ghi nhận **B**, không phải null.
- Khi marking=false, mô hình không queue old value.
- **A, B, C ở đây chỉ là String labels**, không phải heap addresses; queue của model dùng ArrayList nên hoàn toàn không phải bộ buffer của HotSpot.

**Quan trọng:** Trong G1 thật, SATB queue references phải tuân theo các điều kiện về marking và filtering; việc có một old candidate không chứng minh nó còn reachable ở graph hiện tại. Demo không tạo GC cycle hay chứng minh bất kỳ String nào bị thu gom.

## 12. Ví dụ Java 17+: hành vi Java không thay đổi bởi barriers

Write barriers được sinh bởi VM nhưng không tạo ra từ khóa Java mới. Chương trình dưới đây thể hiện thao tác ref fields và array slots mà G1 có thể quan sát nội bộ.

Tạo file **ReferenceMutationDemo.java**:

~~~java
public class ReferenceMutationDemo {
    static final class Box {
        Box next;
        final int id;

        Box(int id) {
            this.id = id;
        }
    }

    public static void main(String[] args) {
        Box root = new Box(1);
        Box first = new Box(2);
        Box second = new Box(3);
        Box[] slots = new Box[2];

        root.next = first;
        slots[0] = root;
        slots[1] = second;

        System.out.println("first=" + root.next.id);
        root.next = second;
        System.out.println("replaced=" + root.next.id);

        slots[1] = null;
        System.out.println("slotCleared=" + (slots[1] == null));
        System.out.println("sameObject=" + (root.next == second));
    }
}
~~~

Chạy:

~~~bash
javac --release 17 -encoding UTF-8 ReferenceMutationDemo.java
java -XX:+UseG1GC ReferenceMutationDemo
~~~

**Stdout:**

~~~text
first=2
replaced=3
slotCleared=true
sameObject=true
~~~

Với chương trình này, **không thể khẳng định** từ source rằng root thuộc old region còn first/second thuộc young region tại một thời điểm cố định: lifetime/generations phụ thuộc allocations, JVM/GC và triggers. Đây chỉ là các **Java reference writes** có thể đi qua barrier infrastructure phù hợp.

Đổi collector có thể đổi thuật toán/barrier strategy nhưng vẫn phải bảo toàn **Java-level output** và memory safety. Đừng dùng stdout như bằng chứng card nào đã dirty.

## 13. Card marking không đồng nghĩa reference tới đối tượng mới

Trong trường hợp:

~~~java
holder.child = other;
holder.child = null;
holder.child = previous;
~~~

Collector có thể ghi nhận card source nhiều lần, nhưng trạng thái cuối chỉ còn reference tới previous. Tương tự, ghi **same value** vào một slot có thể được compiler/VM xử lý khác nhau tùy đường thực thi.

Các kết luận không hợp lệ:

- “Ba assignments = ba RSet entries.”
- “Card dirty = old-to-young hiện còn.”
- “Card clean = suốt lịch sử chưa có assignment.”
- “RSet có một candidate = object đích còn sống.”
- “Cùng một card có hai refs vào hai regions thì chỉ một target RSet được cập nhật.”

Cần phân biệt **event log/dirty hint** với **snapshot của reference slots tại lúc scan**.

### 13.1. False positives và false negatives

Ví dụ card dirty do một tham chiếu vào R3 rồi được overwrite thành null. RSet có thể vẫn có candidate trong một giai đoạn; đó là **false positive candidate** và gây scan overhead, nhưng GC sẽ kiểm tra slot thật.

Nếu có tham chiếu thật từ ngoài CSet trỏ vào một object trong CSet mà collector không ghi nhận qua bất kỳ đường root/remembered metadata phù hợp nào, đó có thể là **false negative nguy hiểm**. Barrier correctness là điều kiện an toàn, quan trọng hơn độ chính xác tuyệt đối từng candidate.

## 14. Concurrent refinement, queues và GC pause

G1 có thể thực hiện một phần việc cập nhật RSet **đồng thời với mutator**. Khi card marking tạo backlog:

~~~text
Mutator threads
  | dirty cards / buffers
  v
Pending work queues
  |
  +-- Concurrent refinement workers
  |       |
  |       +--> Update RSet metadata
  |
  +-- Pending work at collection pause
          |
          +--> Process/merge/update needed metadata
          +--> Scan incoming candidates for CSet
~~~

Các phiên bản HotSpot có thể thay đổi tên phase, queues và processing strategy. Với JDK 17, **Update RS / Scan RS** là các khái niệm thường gặp khi giải thích chi phí pause: cập nhật outstanding remembered-set work và scan candidates.

### 14.1. Khi nào overhead tăng?

Một số yếu tố làm tăng write-barrier/card/RSet cost:

- Mutation rate cao với rất nhiều reference field/array element writes.
- Object graph có nhiều **cross-region edges**.
- Một số regions có incoming candidates dày đặc.
- Card dirtied thường xuyên rồi được refined nhiều lần.
- Backlog dirty cards chưa được xử lý kịp trước GC pause.
- Tỷ lệ scan card cao do **coarse-grained metadata** hoặc stale candidates.
- Allocation/promotion pattern khiến old-to-young references phát sinh nhiều.
- Memory pressure, region sizing và live set thay đổi CSet composition.

Không đoán bằng con số field assignments trong source: JIT, escape analysis, array-copy barriers, null stores, VM safepoints và region placements ảnh hưởng số barrier actions thực.

### 14.2. RSet coarsening

Để tránh sử dụng metadata quá lớn, một remembered-set implementation có thể chuyển từ biểu diễn rất chính xác (ví dụ các card indices) sang biểu diễn **thô hơn** cho một source area/region. Điều này tiết kiệm metadata nhưng khiến collector scan rộng hơn khi cần.

Đó là một trade-off:

~~~text
Precise remembered set:
  nhiều entries / độ chọn lọc cao / metadata lớn

Coarser remembered set:
  ít metadata hơn / có thể scan nhiều card hoặc vùng hơn
~~~

Không phải mọi GC có cùng ngưỡng hoặc cấu trúc hash tables/bitmaps; các flags có thể thay đổi qua JDK. Trên Java 17, nên đo số liệu trước khi chọn tuning thủ công.

## 15. Tránh đồng nhất G1 với mọi collector khác

| Collector/cơ chế | Cách hiểu thích hợp |
| --- | --- |
| **Serial/Parallel generational GC** | Có những cơ chế remembered/card-style tracking cho generational boundary, nhưng thuật toán cụ thể khác G1 |
| **G1** | Region-based, remembered-set candidates, post-write card marking, concurrent SATB pre-barrier khi marking |
| **ZGC Java 17** | Low-latency collector có load barriers/colored pointers và cơ chế concurrency khác; không sao chép nguyên G1 RSet model |
| **Shenandoah** | Low-pause/concurrent collector với barrier set và forwarding/load-reference xử lý khác; tùy distribution/build |
| **Không có GC hoặc collector đặc biệt** | Không nên giả định tồn tại card table giống G1 |

**GC barrier là implementation detail**. Java source vẫn có các types **Object**, **String**, reference fields và array components; không có một kiểu **CardTable** bắt buộc trong Java language spec.

### 15.1. Barrier hiệu lực ở đâu?

Barriers có thể được triển khai bởi interpreter, C1/C2 JIT, stubs/runtime, array-copy paths hoặc những đường ghi đặc biệt. Việc một assignment Java được tối ưu/loại bỏ hoàn toàn nếu object không thoát và không có side effects cũng có thể khiến không có tương ứng một heap write cần card marking.

Không kết luận “mỗi dòng Java gán tham chiếu → luôn 2 barriers”.

## 16. Những quan hệ thường gây nhầm trong sơ đồ

### 16.1. Source vs target region

Cho:

~~~text
A thuộc Region 1
B thuộc Region 4
A.child = B
~~~

- **Source card** nằm tại slot **A.child**, tức trong Region 1.
- **Target object** B nằm trong Region 4.
- **Inbound RSet của Region 4** có thể ghi nhận source card của Region 1.
- Card table thường được lập chỉ mục theo **source slot address** (vị trí field được ghi), không theo target address đơn thuần.

### 16.2. Old-to-young vs young-to-old

~~~text
Old A ---> Young B
Young C ---> Old D
~~~

Trong một young collection:

- **Old→Young** là cạnh từ ngoài vùng đang thu gom vào young; cần root/remembered processing phù hợp.
- **Young→Old** không tự là một incoming root từ old vào young. Khi scan young object C sống, nó có reference D thuộc old; đó là cạnh hướng ngược.
- Với G1 theo regions, cần xét region membership/CSet chứ không chỉ nhãn young/old.

### 16.3. Một card có hai target regions

~~~text
Source card K:
  field x ---> Region 4
  field y ---> Region 7
~~~

Refinement có thể tìm references liên quan đến cả Region 4 và Region 7; inbound metadata của hai targets đều có thể ghi nhận card K hoặc biểu diễn tương ứng. **Card dirty event không chứa bắt buộc một target region duy nhất**.

### 16.4. Source object được GC di chuyển

Khi evacuation di chuyển object, source/target addresses thay đổi. GC phải cập nhật pointers và metadata liên quan, không thể xem “card index của object” như identifier vĩnh viễn gắn với Java object identity.

## 17. Quan sát G1 trên HotSpot Java 17

### 17.1. Xác nhận collector

Có thể khởi chạy một chương trình với G1:

~~~bash
java -XX:+UseG1GC ReferenceMutationDemo
~~~

Nếu lệnh biên dịch và classpath hợp lệ, ví dụ này in stdout như mục 12. Việc bật G1 không tự làm chương trình Java in dirty-card events.

Kiểm tra flags JVM thực:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Tìm **UseG1GC**, **G1HeapRegionSize**, **MaxGCPauseTimeMillis** và các flags phù hợp khác. Mỗi JDK/VM có ergonomics và cách hiển thị khác nhau; không suy final collector chỉ từ một tutorial.

### 17.2. Dùng Unified JVM Logging

Trong HotSpot Java 17:

~~~bash
java -XX:+UseG1GC -Xlog:gc*=info ReferenceMutationDemo
~~~

Một chương trình chạy quá nhanh hoặc cấp phát rất ít có thể **không thực hiện young/mixed GC nào** trong một lần chạy; vì vậy không có một số lượng event cố định để dự đoán.

Để xem available tags:

~~~bash
java -Xlog:help
~~~

Một cấu hình thử nghiệm giàu thông tin hơn trong môi trường chấp nhận nhiều log:

~~~bash
java -XX:+UseG1GC -Xlog:gc*,gc+remset=debug ReferenceMutationDemo
~~~

**Không bảo đảm** mọi output hay tag availability giống nhau trên mọi JVM/JDK build. Xem **java -Xlog:help**, rồi điều chỉnh log level/tag. Không chạy trace log khối lượng lớn trên production trước khi đánh giá overhead/dung lượng.

### 17.3. Điều gì có thể xem từ log?

Tùy bản JDK và logging configuration, bạn có thể thấy:

- Loại pause (young evacuation, concurrent start, mixed...).
- Pause duration, collection set composition/regions.
- Thời gian làm việc cho root scanning, remembered-set processing/merging và object copying.
- Số scanned cards/remembered-set statistics tại những log levels thích hợp.
- Concurrent refinement/marking events và dữ liệu GC pauses.

**GC log là aggregate diagnostics**, không phải bản in chính xác mọi Java field assignment. Không thể suy từ một dòng “Scan RS” rằng ứng dụng đã sửa field nào tại Java source line nào.

### 17.4. Kết hợp profiling và heap graph

Nếu pause cost liên quan remembered sets tăng, hãy kiểm tra:

1. Allocation rate và promotion rate.
2. Cấu trúc objects có rất nhiều cross-region pointers.
3. Mutable collections/arrays chứa nhiều references.
4. Cache retaining old objects rồi liên tục thêm young references.
5. Card refinement backlog và pause breakdown.
6. Heap region size thực được ergonomics chọn.
7. GC algorithm và CPU resources được phân cho concurrent workers.

Nếu vấn đề là memory leak, dùng **heap dump/path-to-GC-root** để xác định graph còn reachable. Write barrier/RSet logs **không thay thế** reachability analysis.

## 18. Cách phân tích một bài tập “A trỏ B” từng bước

Giả sử:

~~~text
Region O1: old object A
Region O2: old object C
Region Y3: young object B
Region Y4: young object D

A.ref = B
C.ref = D
B.ref = C
~~~

Các bước:

1. Xác định **source slot** của từng cạnh: A.ref ở O1; C.ref ở O2; B.ref ở Y3.
2. Xác định **target region**: B ở Y3, D ở Y4, C ở O2.
3. Đánh dấu **cross-region**: cả ba cạnh đều crossing vì source/target regions khác nhau.
4. Với G1 post-write barrier, xét guards/card marking phù hợp khi từng store xảy ra; không khẳng định cùng số queue entries với số edges.
5. Khi refinement, **inbound RSet Y3** có thể ghi nhận source card O1; **inbound RSet Y4** có thể ghi nhận source card O2; **inbound RSet O2** có thể ghi nhận source card Y3 khi chính sách/phase duy trì metadata đó.
6. Khi young CSet gồm Y3/Y4, collector quan tâm đặc biệt tới incoming edges từ **ngoài CSet** (O1 và O2). Cạnh Y3→O2 không phải incoming from outside vào young CSet.
7. Nếu đồng thời SATB marking đang active và một slot bị overwrite, **pre-barrier** có thể enqueue referent cũ, độc lập ý nghĩa RSet.
8. Nếu A.ref sau đó trở thành null, card/RSet candidate có thể stale một thời gian; GC phải kiểm tra actual reference.

**Quan trọng:** Một số phần metadata cho những targets có thể được duy trì chọn lọc. Không xem sơ đồ ở bước 5 là cam kết “G1 luôn có một stored RSet entry cho mọi cross-region edge tại mọi thời điểm”.

## 19. Write barrier và các tính chất của chương trình Java

### 19.1. Không làm thay đổi Java reference identity

~~~java
Object a = new Object();
Object b = a;
System.out.println(a == b); // true
~~~

Dù G1 thực hiện barrier operations khi có reference writes phù hợp, Java-level **==**, **equals()**, **getClass()** và memory-safety guarantees giữ nguyên. Runtime không được để bookkeeping của collector tạo ra object identity khác.

### 19.2. Không thay thế thread synchronization

Nếu hai threads cập nhật một ordinary reference field không volatile/không synchronized, vẫn có thể có data race theo Java Memory Model. GC barriers không biến field ấy thành atomic/volatile publication contract. Thiết kế thread-safe cần dùng Java concurrency mechanisms riêng.

### 19.3. Không phải đối tượng Java để ứng dụng chỉnh sửa

Card table/RSet không phải Collection hay Map công khai cho ứng dụng. Bạn không nên viết code tự sửa metadata GC bằng JNI/Unsafe. Ví dụ Java trong bài chỉ **mô phỏng**, tuyệt đối không thao tác internals của live collector.

## 20. Tối ưu hiệu năng: khi nào nên chú ý?

**Không bắt đầu bằng sửa cờ RSet/card** khi chưa có đo đạc. Nếu GC logs cho thấy remembered-set work/scan là một thành phần đáng kể của pause, hãy kiểm tra nguyên nhân ở **application object graph** và heap ergonomics.

Một số hướng:

- Giảm churn của references trong những long-lived arrays/containers nếu không cần thiết.
- Hạn chế cấu trúc graph với quá nhiều cross-region pointers khi nó không mang giá trị nghiệp vụ.
- Xem cache/queue ownership; cải thiện locality bằng thiết kế data structures phù hợp.
- Đặt heap/region/GC goals dựa trên throughput/latency thực, không chỉ một log line.
- Đánh giá CPU cycles spent in mutator barriers so với GC refinement/scanning.
- Không ép “ít references” bằng cách nhét dữ liệu vào off-heap hoặc primitive buffers nếu gây complexity/rủi ro lớn hơn; cần benchmark toàn hệ.

### 20.1. Trade-offs từ region size

Regions lớn có thể giảm số lượng cross-region boundaries trong một số workload, từ đó giảm metadata/refinement work. Nhưng regions lớn cũng có thể làm thay đổi lượng live data cần evacuate, humongous object handling và pause behavior. **G1HeapRegionSize** là tuning flag dành cho trường hợp có evidence rõ, không phải “càng lớn càng tốt”.

### 20.2. Thay đổi collector

Nếu mục tiêu là latency rất thấp, có thể đánh giá collector khác phù hợp JDK/workload. Tuy nhiên mỗi collector có barrier strategy, CPU/memory overhead, requirement và maturity khác nhau; không chuyển collector dựa trên nhận định rằng “write barrier luôn đắt nên ZGC không dùng barrier”.

## 21. Những hiểu lầm cần tránh

1. **“Write barrier là Java volatile/memory fence.”** Không: GC barrier và JMM synchronization phục vụ vấn đề khác.
2. **“Mọi reference assignment luôn thực hiện đúng hai barrier functions.”** Không: có phase guards/optimizations.
3. **“Pre-write G1 ghi new reference.”** Sai trong vai trò SATB: quan tâm **old value** sắp bị overwrite.
4. **“Post-write G1 ghi old reference để SATB.”** Sai: nhiệm vụ chính ở đây là cross-region/card/RSet tracking.
5. **“Card dirty = có một young object sống.”** Sai: dirty chỉ là candidate; card có thể stale.
6. **“Card table lưu danh sách đầy đủ Java objects.”** Sai: nó mô tả vùng/slot candidates.
7. **“RSet chứa mọi outgoing edges của target region.”** Sai với inbound RSet; nguồn nằm ngoài region.
8. **“RSet là danh sách chính xác tất cả live objects trong region.”** Sai.
9. **“Một assignment tương ứng đúng một RSet entry.”** Sai: batching, card granularity, coalescing.
10. **“G1 chỉ tracking old-to-young.”** Sai: region-based cross-region edges phục vụ young/mixed CSet.
11. **“Old→Young có thể bỏ qua vì object ở old đã được quét trong quá khứ.”** Sai: đồ thị có thể đổi sau đó.
12. **“Quét remembered set có nghĩa quét toàn old heap.”** Không: mục tiêu là quét vùng candidates liên quan.
13. **“Concurrent refinement luôn hoàn tất ngay khi Java store kết thúc.”** Sai: có pending queues.
14. **“Card/RSet false positives đồng nghĩa memory safety sai.”** Sai: có thể chỉ tăng scan work.
15. **“SATB giữ graph đúng y như hiện tại từng nanosecond.”** Không: đó là logical snapshot approximation theo marking invariant.
16. **“Nếu old edge bị xóa thì object chắc chắn thu gom ngay trong marking đó.”** Không: SATB có thể tạo floating garbage.
17. **“GC logs cho biết Java source statement nào làm card dirty.”** Không phải một tính năng mặc định như vậy.
18. **“Dirty card là một GC root độc lập kiểu static field.”** Không: metadata hỗ trợ root/incoming scanning.
19. **“Để sửa memory leak, tắt write barriers.”** Không: barriers là phần bảo đảm an toàn collector; sửa ownership/root paths.
20. **“Giảm card size luôn nhanh hơn.”** Không: metadata, write, refinement và scan có trade-offs.
21. **“RSet precision luôn tuyệt đối.”** Không: có stale/coarse candidates, quan trọng là không bỏ sót references cần thiết.
22. **“ZGC/Shenandoah phải dùng y nguyên G1 cards.”** Không: implementation barriers khác nhau.
23. **“Cứ java -XX:+UseG1GC là sẽ có GC log mọi lần chạy.”** Không nếu không bật logging phù hợp hoặc không có collection.
24. **“G1 pre-barrier hoạt động chỉ ở old-to-young writes.”** Không: mục đích SATB là snapshot preservation khi concurrent marking.
25. **“Collector có quyền làm Java reference semantics thay đổi để tracking nhanh hơn.”** Không: phải bảo toàn ngữ nghĩa Java.

## 22. Bài tập có đáp án

**Bài 1.** Old object O tham chiếu Young object Y. Young GC chỉ scan thread roots và young regions, không scan old-to-young candidates. Có nguy cơ gì?

**Đáp án:** Có thể bỏ sót một đường giữ Y sống qua O. Generational collector cần xem xét old-to-young references qua remembered/card/barrier hoặc cơ chế tương đương.

**Bài 2.** Giả sử card size 512 byte, source slot address offset 1300 tính từ heap base 0. Card index?

**Đáp án:** floor(1300/512)=**2**; card 2 có miền byte [1024,1535].

**Bài 3.** Một card có hai fields trỏ lần lượt Region 5 và Region 8. Cả hai cần được xét khi refine không?

**Đáp án:** Có thể. Một dirty card không giới hạn một target; inbound metadata cho cả regions có thể cần cập nhật theo chính sách collector.

**Bài 4.** Source object A trong Region 1 trỏ target B trong Region 7. Inbound RSet của region nào ghi nhận source card?

**Đáp án:** **Region 7** theo mô hình per-target inbound RSet.

**Bài 5.** Gán A.ref từ B sang null khi G1 SATB concurrent marking active. Pre-barrier quan tâm cái gì?

**Đáp án:** Old referent **B**, có thể được enqueue trước khi overwrite để bảo toàn SATB snapshot invariant.

**Bài 6.** Gán A.ref sang C ở region khác khi không có concurrent marking. G1 pre SATB có bắt buộc enqueue giá trị cũ không?

**Đáp án:** Không như một rule mọi lúc; pre-barrier có kiểm tra marking-active, nhưng post-barrier có thể vẫn tracking cross-region reference phù hợp.

**Bài 7.** Ghi một field 100 lần nhưng chỉ trên một source card. Có chắc 100 RSet entries không?

**Đáp án:** Không. Card-level metadata, duplicate filtering và batch refinement có thể gộp work.

**Bài 8.** Một dirty card sau refine không còn reference sang target region. Dirty event trước đó có nghĩa memory leak không?

**Đáp án:** Không. Nó có thể là stale/false-positive candidate; GC phải kiểm tra actual slots phù hợp.

**Bài 9.** Vì sao G1 có thể xử lý old→old region references?

**Đáp án:** Vì mixed collection có thể chọn một số old regions vào CSet; incoming edges từ old regions khác vẫn cần được xem xét.

**Bài 10.** Có thể suy từ việc RSet chứa một card rằng object đích chắc chắn live?

**Đáp án:** Không. RSet là metadata các source locations tiềm năng; live/dead phụ thuộc roots/tracing và các điều kiện GC.

**Bài 11.** Card marking thuộc compiler/runtime hay được lập trình viên viết thủ công trong Java?

**Đáp án:** Runtime/JIT/interpreter/VM barrier infrastructure; Java source viết phép gán bình thường.

**Bài 12.** GC barrier có thay thế volatile publication giữa threads không?

**Đáp án:** Không. GC bookkeeping độc lập với happens-before/thread synchronization.

**Bài 13.** Trong SATB, vì sao marker có thể cần old reference khi mutator overwrite field?

**Đáp án:** Cạnh thuộc snapshot logic có thể bị xóa trước khi marker scan; old reference giúp tránh bỏ sót các objects cần được xem là live theo snapshot.

**Bài 14.** Một card 512 byte có 32 reference slots, nhưng chỉ một slot trỏ vào CSet. Tại sao collector vẫn scan thêm slots?

**Đáp án:** Card granularity ưu tiên metadata/write efficiency; scan một card có thể bao gồm những slots không liên quan.

**Bài 15.** G1 có bắt buộc dùng cùng queue layout/tracing code như một tutorial JDK 8 ở JDK 17/26 không?

**Đáp án:** Không. Cơ chế nội bộ và flags thay đổi; giữ mô hình invariants và đọc docs/source đúng version.

**Bài 16.** Khi GC pause bị chi phối bởi remembered-set scan, nên làm gì trước?

**Đáp án:** Đo lại bằng G1 GC logs, xem cross-region connectivity/dirty-card rate/region sizing/live set và workload. Tránh chỉnh flags tùy ý.

**Bài 17.** Tại sao model CardRememberedSetModel in inbound2=[1] dù hai writes cùng card?

**Đáp án:** RSet của model lưu **source card candidates**, không đếm số references; hai fields thuộc card 1.

**Bài 18.** Model đã null first nhưng vẫn in afterOneNull=[1] vì sao?

**Đáp án:** Field second trong cùng card vẫn trỏ target region 2; khi refine scan card, candidate vẫn phù hợp.

**Bài 19.** Một source card ở outside CSet trỏ vào two targets trong CSet. Dùng một inbound RSet chung liệu bắt buộc mất thông tin không?

**Đáp án:** Không; metadata có thể map candidate cards vào targets hoặc hợp thành tập cần scan. GC cần đảm bảo mọi incoming reference cần thiết vẫn được xem.

**Bài 20.** Có thể giảm GC work bằng cách bỏ SATB pre-barrier khi concurrent marking không?

**Đáp án:** Không nếu không có một thuật toán/giải pháp đúng thay thế. Tắt cơ chế cần thiết có thể phá marking invariant; người viết application không quản lý barrier này.

## 23. Checklist khi đọc code hoặc phân tích sự cố

- Bắt đầu bằng **loại GC** và JDK build cụ thể.
- Vẽ **cạnh từ source slot → target object**; ghi rõ region membership.
- Với young/mixed CSet, xác định **incoming edges từ ngoài CSet**.
- Phân biệt **card table** (dirty candidate marker) và **remembered set** (incoming sources có thể cần scan).
- Nhớ **source card index** dựa trên nơi field được ghi, không phải chỉ target address.
- G1 **post-barrier** để phục vụ tracking source cards/cross-region updates.
- G1 **pre-barrier** để phục vụ SATB concurrent marking với old referent.
- Queue/refinement có thể batch/delay; không giả định RSet đã cập nhật tức thì sau Java assignment.
- Dùng **false positive vs false negative** để đánh giá tính đúng.
- RSet có thể coarse/stale nhưng phải đủ để tránh mất incoming edges.
- Phân biệt **liveness tracing** với **card bookkeeping** và **object relocation**.
- Khi GC log xấu, đo remembered-set work/scan, object graph topology và mutation rate.
- Không coi memory barrier của JMM là GC write barrier.
- Không nghĩ static cache leak có thể sửa bằng điều chỉnh RSet; phải sửa root/ownership path.
- Khi đổi collector, kiểm tra cơ chế barriers mới; không áp dụng máy móc tài liệu G1 cho ZGC.
- Với Java 17, dùng chính tài liệu Oracle 17/HotSpot logs để tránh dựa vào internal details ở bản khác.

### Tài liệu tham khảo chuẩn và chuyên sâu

- **Oracle Java SE 17 — Garbage-First (G1) Garbage Collector:** https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html
- **Oracle Java SE 17 — G1 Tuning:** https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector-tuning.html
- **Oracle Java SE 17 — Unified JVM Logging trong java command:** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **OpenJDK JDK 17 HotSpot — G1 barrier implementation/source tree:** https://github.com/openjdk/jdk17u/tree/master/src/hotspot/share/gc/g1
- **OpenJDK JDK 17 HotSpot — Card table infrastructure:** https://github.com/openjdk/jdk17u/tree/master/src/hotspot/share/gc/shared
- **JVMS Java SE 17 — Run-Time Data Areas/Heap:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3
- **Java SE 17 — java.lang.ref reachability semantics:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/package-summary.html

**Ghi nhớ cốt lõi:** **Write barriers** giữ thông tin về biến đổi tham chiếu để một collector không bỏ sót các cạnh quan trọng. **Card table** đánh dấu các source areas cần kiểm tra; **remembered sets** mô tả những incoming candidates từ ngoài regions cần thu gom để giảm quét toàn heap. Trong HotSpot G1, **post-write** phục vụ cross-region card/RSet tracking, còn **pre-write** bảo toàn SATB snapshot khi đánh dấu đồng thời. Dirty card và RSet entries là **metadata ứng viên**, không tự chứng minh liveness, và các chi tiết storage/queue/barrier optimization phụ thuộc collector/version.
