# 12.8 Phân biệt shallow size với retained size và vai trò của dominator

## 1. Vì sao hai con số này quyết định cách đọc heap dump?

Khi mở một Java heap dump bằng Eclipse Memory Analyzer (MAT) hay một công cụ phân tích tương đương, bạn thường thấy hai cột **Shallow Heap / Shallow Size** và **Retained Heap / Retained Size**. Chúng trả lời hai câu hỏi khác nhau:

- **Shallow size:** *Bản thân đối tượng này chiếm bao nhiêu byte trên Java heap?*
- **Retained size:** *Đối tượng này đang giữ sống bao nhiêu byte trên heap, tính cả chính nó và những đối tượng sẽ không còn đường được giữ sống nếu nó không còn được tham chiếu?*

Ví dụ: một đối tượng quản lý cache chỉ chiếm vài chục byte shallow, nhưng có thể giữ một đồ thị hàng trăm MB. Ngược lại, một đối tượng trỏ đến một mảng 100 MB **chưa chắc** có retained size thêm 100 MB nếu mảng ấy cũng được giữ sống từ một nhánh khác.

**Dominator tree** giúp tính và nhìn ra phần bộ nhớ do một đối tượng giữ sống **độc quyền** trong đồ thị tham chiếu tại thời điểm dump. Nếu không hiểu dominator, rất dễ cộng trùng bộ nhớ, nhầm “có tham chiếu” với “giữ sống độc quyền”, hoặc kết luận rò rỉ bộ nhớ chỉ vì thấy một giá trị retained lớn.

Bài này tập trung vào **Java heap**: kích thước các object, mảng, quan hệ tham chiếu và GC roots trong snapshot. Java heap dump không phải bản đo đầy đủ RSS của tiến trình, direct/native memory, metaspace hay vùng cấp phát ngoài heap.

## 2. Ba khái niệm phải tách bạch

### 2.1. Shallow size — dung lượng của chính đối tượng

Một Java object cần bộ nhớ cho phần header, các field nằm trong chính object đó (giá trị nguyên thủy hoặc **ô lưu tham chiếu**), và padding/alignment nếu có. Shallow size **không cộng kích thước của đối tượng được field tham chiếu đến**.

Với mảng, phần tử nằm trong chính mảng, nên:

- `byte[1_000_000]` có shallow size xấp xỉ 1.000.000 byte **cộng header và phần căn chỉnh**; không được khẳng định một con số chính xác nếu chưa biết JVM layout.
- `int[1_000_000]` chứa khoảng 4.000.000 byte dữ liệu nguyên thủy, ngoài header/alignment.
- `Object[1_000_000]` chứa một triệu **ô tham chiếu** trong shallow size của mảng. Nếu một ô trỏ đến đối tượng 5 MB thì **5 MB đó không tự động cộng** vào shallow của `Object[]`.
- `ArrayList` là một object riêng; mảng backing `Object[]`, các phần tử và đồ thị phía sau là những object khác.
- `String` là một object riêng; mảng lưu nội dung ký tự/byte, nếu có, là một object khác theo bố cục của JDK đó.

Chi tiết header, kích thước reference, nén con trỏ (`UseCompressedOops` và các cài đặt liên quan), alignment, loại mảng, JVM/JDK và định dạng dump ảnh hưởng đến số shallow size thực tế. Một sơ đồ “object header luôn 12 byte, reference luôn 4 byte” **không phải chân lý cho mọi JVM**.

Minh họa:

```java
final class Box {
    byte[] payload = new byte[1024 * 1024];
}
```

Đây là **đoạn mã minh họa, không phải chương trình độc lập**. Đối tượng `Box` có shallow size nhỏ vì field `payload` chỉ lưu tham chiếu. Mảng `byte[]` mới chứa dữ liệu cỡ 1 MiB. Nếu mảng đó chỉ có một đường được giữ sống thông qua `Box` thì retained size của `Box` có thể lớn hơn shallow size rất nhiều; nếu mảng có đường giữ sống độc lập khác, kết quả khác.

### 2.2. Reachable graph — mọi thứ có thể đi tới bằng tham chiếu

Gọi `Reach(X)` là tập đối tượng có thể đi từ X qua các cạnh tham chiếu trong đồ thị. Đây là một khái niệm **đi theo hướng từ object tới các object nó tham chiếu**.

Nhưng chỉ vì X trỏ tới Y **không có nghĩa Y sẽ bị thu gom nếu X biến mất**. Một đối tượng khác Z cũng có thể trỏ tới Y, hoặc Y có đường tham chiếu khác từ GC root. Vì vậy, **tổng shallow size của toàn bộ `Reach(X)` không phải retained size của X**.

### 2.3. Retained size — phần heap được giữ sống độc quyền

Về mặt đồ thị, với tập nút có thể truy cập từ GC roots và quy tắc reachability của công cụ đang dùng:

- `RetainedSet(X)` gồm X và những đối tượng mà **mọi đường đi từ GC root đến chúng đều phải đi qua X**.
- `RetainedSize(X) = Σ ShallowSize(Y)` với mọi `Y ∈ RetainedSet(X)`.

Retained size là **tổng shallow size của một tập object**, không phải một kích thước đo độc lập của “đồ thị con vật lý”. Nó thường được diễn giải như lượng Java heap *có khả năng* được giải phóng khi **mọi đường giữ sống X bị loại bỏ**, các đường giữ sống khác không thay đổi và GC đủ điều kiện thu gom.

Trong một snapshot, retained size của một object không nhỏ hơn shallow size của chính nó theo định nghĩa tập giữ lại có chứa X. Nhưng retained size có thể **thấp hơn rất nhiều** tổng kích thước của mọi object X trỏ tới do chia sẻ tham chiếu.

| Thuộc tính | Shallow size | Retained size |
| --- | --- | --- |
| Phạm vi | Chỉ object X, gồm header/field/array elements/padding | X và các object bị X **dominate** |
| Câu hỏi | “Object này tự chiếm bao nhiêu?” | “Nhánh này độc quyền giữ sống bao nhiêu?” |
| Có tính object tham chiếu tới? | Không | Có, **chỉ nếu không còn đường từ root đi vòng qua X** |
| Dễ gặp ví dụ lớn | Mảng `byte[]`, `int[]`, `Object[]` dung lượng lớn | Cache manager, map root, session manager, classloader, thread holder |
| Có bằng file `.hprof`, RSS, `-Xmx`? | Không | Không |
| Có chứng minh memory leak? | Không | Không, cần so sánh với vòng đời nghiệp vụ và nhiều bằng chứng |

## 3. GC roots và tại sao “ai giữ sống ai” quan trọng

Garbage collector nhìn vào những **GC roots**: các điểm gốc mà VM coi là đang được giữ sống, ví dụ tham chiếu từ thread stack, static fields của các lớp đang hoạt động, JNI handles và các cấu trúc runtime khác. Từ roots, nó lần theo các tham chiếu có hiệu lực để xác định object còn reachable.

Trong heap dump, một object có thể có nhiều **incoming references** từ những nơi khác nhau. Đường `GC root → ... → object` giải thích vì sao object vẫn còn trên heap. Đừng nhầm:

- **Outgoing reference:** X có field hoặc phần tử mảng trỏ tới Y.
- **Incoming reference:** có object khác trỏ tới X.
- **Path to GC roots:** một hoặc nhiều chuỗi đi ngược từ X đến root.
- **Dominator:** nút nằm trên **mọi** đường đi từ root đến một nút khác; định nghĩa chặt hơn “có một reference”.

Công cụ có thể xử lý khác nhau đối với tham chiếu `WeakReference`, `SoftReference`, `PhantomReference` và đối tượng không reachable. Khi kiểm tra vì sao object bị giữ sống, chú ý lựa chọn loại trừ weak/soft reference paths và quy tắc reachability của snapshot; **một cạnh hiển thị trong dump không mặc nhiên là một strong reference ngăn GC thu hồi object**.

## 4. Dominator: định nghĩa, immediate dominator và cây thống trị

Giả sử ta thêm một **super-root ảo** nối đến mọi GC root đang xét. Trong đồ thị có hướng từ super-root:

> Nút A **dominates** nút B khi **mọi đường đi** từ super-root đến B đều đi qua A.

Mỗi nút được coi là dominate chính nó. Nếu A khác B mà A dominates B thì A là **strict dominator** của B. **Immediate dominator** của B, ký hiệu `idom(B)`, là strict dominator gần B nhất. Mỗi object reachable (trừ super-root) có một immediate dominator trong cách dựng cây này.

**Dominator tree** nối mỗi nút B với `idom(B)`. Cây có các thuộc tính quan trọng:

1. Các node nằm trong **subtree của A** chính là tập đối tượng bị A dominate, tức retained set của A.
2. Cộng shallow size của các node trong subtree A cho ra retained size của A.
3. **Cạnh trên dominator tree không nhất thiết là cạnh tham chiếu trực tiếp trong chương trình Java.** Nó biểu diễn quan hệ phụ thuộc để được giữ sống. Để xem field nào trỏ tới field nào, phải mở incoming/outgoing references hoặc path to GC roots trong **object graph gốc**.
4. Hai nhánh sibling trên dominator tree không giữ trùng object; còn retained set của **cha và con thì chồng lấp**. Không cộng retained size của cha và con để tính tổng heap vì sẽ đếm trùng.

### 4.1. Ví dụ bằng đồ thị có object được chia sẻ

Giả sử có bảy object với shallow size **giả định** (đơn vị B chỉ dùng để tính tay, không phải header/layout có thật của JVM). Có hai đường gốc độc lập:

```text
GC root R1 ──> A:Cache(40) ──> B:Map(64) ──> C:Entry(24) ──> D:Payload(1024)
                    │
                    └──────────────────────────┐
                                               v
                                          S:Shared(512)
                                               ^
                    ┌──────────────────────────┘
                    │
GC root R2 ──> E:Service(48) ───────────────────┘
                    │
                    └────────────> F:Audit(256)
```

Đường đến `S:Shared` có hai cách: `R1 → A → S` và `R2 → E → S`. Do đó A **không dominate** S, E cũng **không dominate** S. Ngược lại, mọi đường đến D đều qua A, B, C; A, B và C đều dominate D.

**Dominator tree suy ra:**

```text
super-root
├── A:Cache
│   └── B:Map
│       └── C:Entry
│           └── D:Payload
├── E:Service
│   └── F:Audit
└── S:Shared
```

Lưu ý đường `super-root → S` là **cạnh thống trị trong cây**, không phải reference trực tiếp có trong chương trình. Một object có nhiều incoming references từ hai nhánh thường làm ta bất ngờ khi thấy nó xuất hiện ngoài subtree của từng nhánh ấy.

### 4.2. Tính tay, không cộng trùng

| Object | Shallow giả định | Retained set | Retained size |
| --- | ---: | --- | ---: |
| D:Payload | 1.024 B | D | 1.024 B |
| C:Entry | 24 B | C, D | 1.048 B |
| B:Map | 64 B | B, C, D | 1.112 B |
| A:Cache | 40 B | A, B, C, D | **1.152 B** |
| F:Audit | 256 B | F | 256 B |
| E:Service | 48 B | E, F | **304 B** |
| S:Shared | 512 B | S | **512 B** |

Tổng shallow của toàn bộ bảy object là `40 + 64 + 24 + 1024 + 48 + 256 + 512 = 1968 B`. Nhưng tập object **có thể đi tới từ A** gồm A, B, C, D, S và có tổng shallow `1664 B`. Retained size của A chỉ là `1152 B` vì S vẫn được E giữ sống khi A không còn được giữ sống.

Nếu chỉ bỏ đường root `R1 → A`, ta giải phóng về mặt lý thuyết **1.152 B**, còn S vẫn sống nhờ E. Nếu chỉ bỏ `R2 → E`, có thể giải phóng **304 B**. Nếu bỏ **cả hai** đường cùng lúc, S cũng không còn được giữ sống, nên cả bảy object (1.968 B) đều có thể được thu gom. Kết quả **không bằng phép cộng giản đơn** retained(A) + retained(E), vì nhóm hai object có retained set chung rộng hơn tổng hai retained set xét riêng.

Cũng không được cộng retained(A) + retained(B) vì B, C, D nằm trong **cả hai** retained set. Trong một cây, các giá trị retained của nút cha đã chứa giá trị retained của các nút con.

### 4.3. Hai phản ví dụ dễ nhầm

**Có tham chiếu nhưng không dominate:** A trỏ đến S và E cũng trỏ đến S. A có outgoing reference đến S nhưng không giữ sống S độc quyền. Việc tìm thấy một field `A.shared` trỏ S không đủ để cộng S vào retained(A).

**Có chu trình nhưng chưa chắc leak:** A trỏ B, B trỏ A. Nếu một GC root chỉ có đường đến A rồi đến B, A có thể dominate B; nếu **không còn đường từ GC roots đến cả hai**, GC có thể thu gom chu trình. Java GC không dựa thuần vào reference counting, nên chu trình tham chiếu tự nó không phải bằng chứng rò rỉ.

## 5. Đọc retained size đúng trong Eclipse Memory Analyzer (MAT)

### 5.1. Histogram trả lời “đang có nhiều object loại nào?”

Mở heap dump, chọn **Histogram**; xem `Class Name`, `Objects`, `Shallow Heap`. Với nhóm object cùng class, shallow heap thông thường là tổng shallow của những instance thuộc nhóm. Ví dụ một triệu `byte[]` hoặc rất nhiều `HashMap$Node` có thể chiếm đáng kể, nhưng histogram chưa trả lời **ai giữ chúng sống**.

Cột retained ở cấp **tập object / class** có thể cần chạy lệnh tính riêng; MAT phân biệt tính **Minimum Retained Size** (ước lượng dưới nhanh hơn) với tính retained size đầy đủ cho một tập. **Không cộng retained size của từng instance hoặc từng class để ra tổng heap:** retained sets có thể giao nhau; cùng một object có thể bị dominate bởi nhiều ancestor ở các cấp khác nhau.

### 5.2. Dominator Tree trả lời “đầu mối nào giữ phần heap lớn?”

Chọn **Dominator Tree**, thường sắp theo **Retained Heap** giảm dần. Mở rộng các subtree lớn để xem cấu trúc giữ sống:

- Một manager/caching object **shallow nhỏ, retained rất lớn** có thể là nơi nắm references tới lượng dữ liệu lớn.
- Một `byte[]` **shallow lớn** có thể cũng có retained lớn gần bằng shallow, nhưng muốn sửa vấn đề phải đi ngược tìm **đối tượng, collection hoặc root đang giữ mảng này sống**.
- Một cache xuất hiện giữ sống nhiều đối tượng có thể là hành vi **hợp lệ** nếu cache có giới hạn và chính sách hết hạn. Retained lớn cho thấy **quy mô đang được giữ**, không chứng minh **giữ quá thời hạn nghiệp vụ**.

Trong Dominator Tree, nhấp vào object đáng ngờ, xem **outgoing references** để biết các thành phần nó trỏ tới; xem **incoming references / Path to GC Roots** để tìm lý do nó vẫn sống. **Dominator Tree là bản đồ phụ thuộc giữ sống, còn Path to GC Roots và references là bằng chứng về các cạnh tham chiếu thực.**

### 5.3. Path to GC Roots: tìm đúng đường giữ sống

Với object hoặc collection nghi ngờ:

1. Chọn object trong MAT rồi mở **Path to GC Roots**; nếu cần, dùng biến thể **exclude weak/soft/phantom references** phù hợp trong công cụ để tập trung vào strong retaining paths.
2. Tìm root có liên quan: static field, live thread, ThreadLocal chain, JNI global ref, loader, session/cache registry, listener, executor queue...
3. Đọc từng field và container trong đường đi; xác định object nào **đáng lẽ phải hết vòng đời** nhưng vẫn còn được tham chiếu.
4. Nếu có **nhiều đường từ các roots khác nhau**, việc cắt một đường có thể không giải phóng object. Điều này giải thích tại sao retained size của một nhánh nhỏ hơn tổng object nó có thể reach được.
5. Gắn đường tham chiếu với luồng nghiệp vụ: lúc nào tạo entry, ai xóa, có TTL/size bound không, thread/loader có kết thúc không?

**Ví dụ diễn giải đúng:** `static Map<Id,Session>` chứa 200.000 session, trong khi chỉ khoảng 10.000 session đang hoạt động. Nếu path to roots đi qua static map, retained của map rất lớn và dữ liệu theo thời gian tiếp tục tăng, giả thuyết thiếu eviction có cơ sở. Vẫn phải kiểm tra chính sách phiên, load và tuổi entry; một snapshot đơn lẻ không chứng minh leak.

## 6. Thực hành với Java 17+ và một HPROF có object dùng chung

Ví dụ dưới đây tạo hai holder có **mảng riêng** và cùng trỏ đến **một mảng dùng chung**. Các field static giữ holder sống để có thể quan sát khi dump. Chương trình chạy độc lập trên JDK 17+; yêu cầu mở terminal tương tác để giữ tiến trình đang sống.

Lưu thành file `RetainedSizeLab.java`:

```java
public final class RetainedSizeLab {
    private static volatile Holder cache;
    private static volatile Holder service;

    static final class Holder {
        final byte[] unique;
        final byte[] shared;

        Holder(byte[] unique, byte[] shared) {
            this.unique = unique;
            this.shared = shared;
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] common = new byte[512 * 1024];

        cache = new Holder(new byte[1024 * 1024], common);
        service = new Holder(new byte[256 * 1024], common);

        // Loại tham chiếu local dư thừa; hai holder vẫn cùng giữ common.
        common = null;

        System.out.println("Heap graph ready");
        System.out.println("Press Enter to stop");
        System.in.read();
    }
}
```

Biên dịch và chạy ở **terminal thứ nhất**:

```bash
javac RetainedSizeLab.java
java -Xms128m -Xmx128m RetainedSizeLab
```

Stdout trước khi nhấn Enter, **chính xác với chương trình này**:

```text
Heap graph ready
Press Enter to stop
```

Giữ chương trình tại dòng chờ nhập. Mở **terminal thứ hai** và xác định PID ứng dụng:

```bash
jcmd -l
jcmd 12345 GC.heap_dump retained-size.hprof
```

Thay `12345` bằng PID thực từ `jcmd -l`. Lệnh `GC.heap_dump` tạo HPROF; với JDK 21, mặc định yêu cầu **full GC trước dump**, trừ khi chọn `-all`. Lệnh có ảnh hưởng lớn đến ứng dụng và có thể gây pause dài; chỉ chạy ở môi trường và thời điểm phù hợp. Đảm bảo đường dẫn dump có quyền ghi và đủ dung lượng. Nếu dùng tên file tương đối, lưu ý nó được giải quyết trong bối cảnh tiến trình JVM đích; dùng đường dẫn tuyệt đối để quản lý kết quả dễ hơn. Dump có thể chứa dữ liệu nhạy cảm nên cần kiểm soát quyền truy cập.

**Quan sát kỳ vọng trong MAT, không khẳng định byte số cố định:**

- Có hai instance `RetainedSizeLab$Holder` được giữ qua hai field static `cache` và `service`.
- Mảng unique của `cache` chứa **1.048.576 phần tử byte**, của `service` chứa **262.144 phần tử byte**; cả hai có shallow size lớn theo payload cộng header/alignment.
- Mảng `common` có **524.288 phần tử byte** và có ít nhất hai đường tham chiếu từ hai holder. Khi xem object graph, cả `cache.shared` và `service.shared` đều dẫn đến cùng **một object `byte[]`**, không phải hai mảng khác nhau.
- Trong dominator tree, mảng common **không nằm trong retained set độc quyền** của riêng holder cache hoặc service, do có đường giữ sống đi qua holder còn lại.
- Holder có shallow size rất nhỏ so với retained size các mảng unique. **Giá trị retained cụ thể** còn chịu ảnh hưởng JVM layout, root/class metadata, thread stack tại thời điểm dump và cách MAT diễn giải snapshot; hãy xem số thực thay vì gán con số từ sơ đồ giả định ở mục 4.

Để so sánh:

1. Mở `retained-size.hprof` trong MAT và tìm `RetainedSizeLab$Holder` ở Histogram.
2. Chuyển sang Dominator Tree, xem vị trí hai holder và mảng `byte[]` chúng giữ.
3. Dùng outgoing references trên cả hai holder, đối chiếu object identity của `shared`.
4. Trên mảng chung, dùng Path to GC Roots; quan sát nhiều đường giữ sống.
5. Nếu thử sửa chương trình để chỉ còn **một holder** trỏ đến common, lấy **một dump mới** và so sánh: lúc đó common có thể chuyển vào retained set của holder còn lại. Cần kiểm tra root paths thực tế vì trạng thái stack, JIT và cách công cụ dựng GC roots cũng ảnh hưởng kết quả.

**Vì sao không lấy retained size bằng `Instrumentation.getObjectSize`?** Phương thức này chỉ cho kích thước lưu trữ của **object được truyền vào** theo JVM implementation; nó **không tự tính đệ quy đồ thị, reachability, GC roots hoặc dominators**. Kết quả đó không thay thế phân tích retained size bằng heap graph.

## 7. Ba phép tính sai thường dẫn đến kết luận sai

### Sai lầm 1: “Tổng outgoing objects = retained size”

Nếu X giữ reference tới Y và Z, bạn cộng shallow(X) + shallow(Y) + shallow(Z). Cách đó chỉ cộng một số node reachable, có thể vừa **bỏ sót** node sâu hơn, vừa **đếm nhầm** node được chia sẻ. Phải xác định những object thực sự **bị X dominate**.

### Sai lầm 2: “Cộng retained của mọi hàng lớn nhất ra tổng dùng heap”

Giả sử A dominate B và B dominate C. Khi đó:

- `retained(A)` **đã chứa** `shallow(B)`, `shallow(C)`.
- `retained(B)` **đã chứa** `shallow(C)`.
- Cộng `retained(A) + retained(B) + retained(C)` khiến C bị tính ba lần.

Muốn tính tổng bộ nhớ của **một tập object**, cần xác định retained set của **cả tập** và lấy hợp tập không trùng, hoặc dùng các nhánh độc lập phù hợp. Trong MAT, tính retained của một nhóm object là một thao tác khác phép cộng đơn giản các cột.

### Sai lầm 3: “Retained size lớn chứng minh memory leak”

Một cache 2 GB có thể hoàn toàn đúng nếu giới hạn được thiết kế là 2 GB và vẫn có nhu cầu lưu. Một listener map 20 MB lại có thể là leak nếu giữ hàng chục nghìn listener đã bị unsubscribe về mặt nghiệp vụ. Retained size cho thấy **tác động lên heap nếu giữ object sống**, còn leak liên quan đến **vòng đời ngoài ý muốn**, cần thời gian, ngữ cảnh và bằng chứng phát sinh/giải phóng.

## 8. Các tình huống thực tế: suy luận đúng từ heap dump

### 8.1. `HashMap`, `ArrayList`, cache và session store

Một manager có thể giữ `Map`, các object entry, key/value, mảng bucket, chuỗi, payload. Shallow của manager rất nhỏ; retained có thể lớn nếu không ai khác giữ phần lớn entries. Khi điều tra:

- Đo count, capacity, tuổi record, tỷ lệ hit/miss hoặc số session còn thực sự hợp lệ.
- Xem **dominator** để tìm manager/collection nắm dung lượng lớn.
- Xem **Path to GC Roots** để biết ai giữ manager sống (singleton, static, thread, component/container).
- Đọc chính sách eviction/TTL/size limit; một map lớn không mặc nhiên leak.

Đặc biệt, một **mảng backing có capacity lớn** có thể tốn shallow dù mới dùng ít phần tử. Đây là hướng tối ưu khác với leak do object không còn cần thiết.

### 8.2. `ThreadLocal` và thread pool

Một worker thread có thể tồn tại lâu hơn request. Nếu dữ liệu request được gắn `ThreadLocal` rồi không xóa, path to roots có thể đi qua thread, `ThreadLocalMap` và value; retained có thể lớn dù request đã kết thúc. Khi hợp đồng vòng đời yêu cầu cleanup, dùng `try/finally` để `remove()`.

Không suy luận rằng chỉ cần xóa key `ThreadLocal` là toàn bộ value lập tức biến mất: quá trình dọn stale entries của `ThreadLocalMap` và các reference khác cần được xem trong ngữ cảnh. Phân tích **chuỗi giữ sống thực tế trong snapshot**.

### 8.3. Listener, callback, executor queue và classloader

- Listener còn trong một list sau khi màn hình/đối tượng đăng ký đã đóng có thể giữ nhiều view model/payload.
- Task ở executor queue có thể giữ request context lớn trong thời gian chờ.
- Classloader không unload có thể giữ class metadata liên quan và những static references của các lớp được tải. Khi điều tra redeploy/plugin leak, xem **classloader tree**, GC roots, thread context classloader và object được liên kết.
- Nếu có shared references giữa nhiều manager, không quy toàn bộ shared subtree cho manager đầu tiên mình thấy.

### 8.4. Một dump và nhiều dump

Một heap dump chỉ là **ảnh chụp**. Nó cho thấy ai đang giữ object sống **lúc đó**; nó thường **không cho biết stack trace nơi object được tạo ra**. Để điều tra xu hướng:

1. Chụp tại các mốc tương đương về workload, sau giai đoạn warm-up.
2. So sánh class count, total shallow, retained roots/subtrees và phân bố tuổi dữ liệu.
3. Đối chiếu GC logs, heap after-GC/live set, JFR allocation events, profiler, traffic, cache policy và throughput.
4. Tìm nhóm object tăng liên tục mà không được giải phóng theo đúng vòng đời.
5. Kiểm tra sau fix liệu retained set/root path bất thường đã biến mất và memory/latency có cải thiện không.

Dữ liệu giữa các dump có thể biến đổi do thời điểm dump, GC trước dump, thread stack hoặc cách công cụ loại bỏ unreachable objects. **Không lấy chênh lệch hai retained sizes làm bằng chứng duy nhất về lượng memory leak**.

## 9. Đọc kết quả: một quy trình điều tra có thể lặp lại

| Bước | Xem ở đâu | Câu hỏi cần trả lời | Tín hiệu chuyển bước |
| --- | --- | --- | --- |
| 1 | Overview, Histogram | Heap chứa object loại nào nhiều? Shallow lớn tập trung ở đâu? | Có nhóm class/array chiếm dung lượng đáng kể |
| 2 | Dominator Tree | Object/manager nào giữ độc quyền subtree lớn nhất? | Có owner kỹ thuật cụ thể, retained lớn |
| 3 | Outgoing References | Owner đang giữ những map, entry, arrays, payload nào? | Hiểu cấu trúc và dung lượng của subtree |
| 4 | Incoming References, Path to GC Roots | Root nào khiến owner không được GC? Có nhiều đường độc lập? | Xác định reference chain thật |
| 5 | Domain lifecycle | Object đó đáng lẽ còn sống không? TTL, close, unregister, remove đúng không? | Có giả thuyết giữ quá vòng đời |
| 6 | Theo dõi thời gian, profiler/JFR | Tập object có tích tụ dưới cùng workload không, allocation ở đâu? | Có bằng chứng đủ mạnh để sửa nguyên nhân |
| 7 | Sau khi sửa | Retained subtree, heap after-GC, CPU/latency có giảm? | Khẳng định hiệu quả bằng phép đo độc lập |

**Quyết định sửa ở đâu:** retained size chỉ giúp **ưu tiên khu vực chứa bộ nhớ**. Root path chỉ ra ai giữ reference; đoạn mã tạo object có thể nằm ở chỗ khác; nguyên nhân leak có thể là quên xóa khỏi map, quên unregister listener, cache không có TTL, thread không kết thúc hoặc xử lý dữ liệu quá mức. Phải nối cả ba: **retained subtree → root path → quy tắc vòng đời của ứng dụng**.

## 10. Giới hạn và lưu ý khi dùng số liệu

- **Heap dump ≠ RSS:** dump tập trung vào Java object graph. Direct `ByteBuffer`, native allocations, thread stacks ngoài heap, code cache, metaspace và overhead của VM không được phản ánh đầy đủ như memory của OS.
- **Snapshot ≠ thời gian:** muốn biết object được tạo khi nào và ở stack nào, kết hợp JFR/allocation profiler; retained size không tự mang allocation history.
- **GC roots và reference types:** weak/soft/phantom references, JNI và thread stack có semantics riêng. Một số đối tượng trong dump có thể chưa reachable theo chế độ phân tích hoặc sẽ được GC sau đó.
- **JVM layout không tuyệt đối:** so sánh shallow giữa hai JDK/config khác nhau cần xem compressed refs, object alignment, collector/build và cách parser diễn giải.
- **Dump mặc định có thể ảnh hưởng hệ thống:** `jcmd GC.heap_dump` trên JDK 21 thường yêu cầu full GC và tiêu thụ CPU/I/O/disk; `-all` không phải “dump miễn phí” và còn bao gồm unreachable objects.
- **Bảo mật:** heap dump có thể chứa token, chuỗi truy cập, dữ liệu khách hàng và object nhạy cảm. Chỉ lưu/chia sẻ theo phạm vi cho phép, xóa hoặc bảo vệ dump khi điều tra kết thúc.
- **Kích thước file dump ≠ retained size:** HPROF có bảng lớp/metadata và encoding riêng; compressed hoặc uncompressed file không trực tiếp biểu diễn tổng shallow heap.

## 11. Bài tự kiểm tra

**Câu 1.** A trỏ B, B trỏ C, nhưng root thứ hai cũng trỏ trực tiếp C. A có dominate C không?

*Trả lời:* Không. Có đường từ root thứ hai đến C mà không qua A. A có thể reach C nhưng không giữ sống C độc quyền.

**Câu 2.** Một object `Controller` có shallow 48 B, retained 250 MiB. Có thể kết luận controller tự chiếm 250 MiB không?

*Trả lời:* Không. 48 B là shallow của controller; 250 MiB là tổng shallow của controller và những object nó dominate trong snapshot. Phải mở subtree để biết những object nào chiếm phần lớn.

**Câu 3.** A dominate B và retained(A) = 80 MiB, retained(B) = 60 MiB. Có thể nói hai object này “dùng 140 MiB” không?

*Trả lời:* Không. 60 MiB của B nằm trong 80 MiB của A. Phép cộng đếm trùng.

**Câu 4.** Nếu một `HashMap` có retained 500 MiB, điều gì phải kiểm tra trước khi gọi đó là leak?

*Trả lời:* GC root/path giữ map sống, số lượng và loại entries, policy TTL/eviction, số entry hợp lệ theo nghiệp vụ, thay đổi qua nhiều snapshot, GC/live-set trend.

**Câu 5.** Vì sao sau khi xóa một field tham chiếu, bộ nhớ RSS chưa chắc giảm ngay?

*Trả lời:* Object có thể còn đường giữ sống khác; GC chưa chạy/thu hồi hoặc heap vẫn committed; RSS còn gồm native/off-heap và phần heap được JVM giữ lại để tái sử dụng. Retained size dự đoán cấu trúc giữ sống trong snapshot, không bảo đảm RSS giảm tức thì.

## 12. Checklist dùng trong sự cố heap tăng

- [ ] Đã phân biệt **shallow** của object/array với **retained** của subtree.
- [ ] Đã biết retained được tính từ **dominator tree** và không cộng trùng retained của cha/con.
- [ ] Đã xác minh **mọi đường tới object đều đi qua dominator**; lưu ý shared references.
- [ ] Đã mở **Path to GC Roots** và xem field/reference chain thật.
- [ ] Đã kiểm tra **weak/soft references**, stack/static/JNI roots và cấu hình parser có liên quan.
- [ ] Đã đối chiếu số liệu với **vòng đời nghiệp vụ**: cache, session, listener, ThreadLocal, queue, classloader.
- [ ] Đã tách **Java heap** khỏi direct/native/RSS và **snapshot** khỏi xu hướng theo thời gian.
- [ ] Có bằng chứng **trước/sau** và kế hoạch đo lại sau thay đổi.

**Điều cần nhớ:** *shallow size* đo dung lượng của **một object**; *retained size* đo phần Java heap mà object đó **giữ sống độc quyền** trong snapshot; **dominator** là điều kiện đồ thị giúp xác định chính xác quan hệ giữ sống ấy. Khi thấy retained lớn, hãy dùng **dominator tree** để định vị vùng nhớ, **path to GC roots** để tìm đường giữ sống và **vòng đời nghiệp vụ** để kết luận có leak hay không.

## Tài liệu đối chiếu

- Eclipse Memory Analyzer — [Shallow vs. Retained Heap](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/shallowretainedheap.html).
- Eclipse Memory Analyzer — [Dominator Tree](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/dominatortree.html).
- Eclipse Memory Analyzer — [Path to GC Roots](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/reference/inspections/path_to_gc_roots.html).
- Eclipse Memory Analyzer — [Basic Tutorial / Histogram và Dominator Tree](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/gettingstarted/basictutorial.html).
- Eclipse Memory Analyzer — [Heap Dump](https://help.eclipse.org/latest/topic/org.eclipse.mat.ui.help/concepts/heapdump.html).
- Oracle JDK 21 — [jcmd: GC.heap_dump](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).