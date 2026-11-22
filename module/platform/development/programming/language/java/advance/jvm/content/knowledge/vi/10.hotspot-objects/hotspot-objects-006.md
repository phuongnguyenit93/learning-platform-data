# Tham chiếu được cập nhật khi GC di chuyển đối tượng trong HotSpot

Trong Java, bạn có thể giữ nhiều biến cùng trỏ tới **một object**, truyền nó qua nhiều method, đặt vào array, collection hoặc field, rồi hệ thống vẫn đọc được object ấy sau các lần Garbage Collection (GC). Tuy nhiên, trong nhiều collector của HotSpot, một số **object còn sống được sao chép hoặc di chuyển tới địa chỉ heap mới**. Làm thế nào mọi tham chiếu vẫn hoạt động? Vì sao `a == b` vẫn `true` dù byte biểu diễn tham chiếu có thể thay đổi? Và khi nào một collector thực sự viết lại reference slot, khi nào nó dùng forwarding hoặc barriers?

**Ý chính:** Java reference là cách chương trình tham chiếu tới **cùng một object logic**, không phải lời hứa về một địa chỉ vật lý cố định. Khi collector có di chuyển object, HotSpot dùng các cấu trúc theo dõi đối tượng và những cơ chế cập nhật/chuyển hướng tham chiếu để code Java luôn thấy object đúng. Phương pháp cụ thể phụ thuộc collector, GC phase và JDK version.

Bài học tập trung vào **HotSpot Java 17**, đặc biệt cơ chế G1 evacuation, đồng thời chỉ ra sự khác biệt về thời gian cập nhật reference giữa collector stop-the-world và concurrent relocating collectors như ZGC hoặc Shenandoah. Khi nói về GC roots, `oop`, forwarding pointer, load/write barriers hay remembered sets, đây là **chi tiết triển khai HotSpot**, không phải biểu diễn raw reference do Java Language Specification (JLS) bảo đảm.

## 1. Vấn đề gốc: “đổi chỗ object” khác “đổi danh tính object”

Xét object graph:

```text
Trước GC:

GC root: local x --------┐
GC root: local alias ----┤
Holder.field ------------┤
Array[0] ----------------┤
                         v
                  [Object A]  địa chỉ giả định 0x1000
                      |
                      v
                  [Object B]  địa chỉ giả định 0x1800

Sau một lần GC có di chuyển A:

GC root: local x --------┐
GC root: local alias ----┤
Holder.field ------------┤
Array[0] ----------------┤
                         v
                  [Object A]  địa chỉ giả định 0x9000
                      |
                      v
                  [Object B]  nơi ở tùy collector/GC phase
```

Các địa chỉ `0x1000` và `0x9000` ở đây **chỉ là ký hiệu minh họa**, không phải địa chỉ lấy từ một JVM thật.

Nếu collector đã đưa A từ một vùng heap sang vùng mới, tất cả những **đường tham chiếu còn cần thiết và có thể được sử dụng** phải tiếp tục chỉ tới A về mặt ngữ nghĩa. Với một collector copy/evacuate stop-the-world, các reference slots thích hợp được cập nhật trước khi application threads tiếp tục. Với một collector di chuyển đồng thời, chương trình có thể đi qua barriers/forwarding logic, nên không nhất thiết mọi slot đã mang bit của vị trí mới trong cùng một khoảnh khắc.

Hai phát biểu cần phân biệt:

- **Object identity không đổi:** A vẫn là A, giá trị field và quan hệ aliasing được bảo toàn trong quá trình di chuyển hợp lệ.
- **Địa chỉ lưu trữ có thể đổi:** byte representation hoặc location mà HotSpot dùng để tìm A có thể thay đổi; địa chỉ ấy **không phải Java-level identity**.

Vì vậy, một biến reference Java không nên được hiểu là “hằng số địa chỉ C pointer” mà ứng dụng có thể lưu thành `long` rồi sử dụng tùy ý.

## 2. Java bảo đảm điều gì, HotSpot làm việc gì?

| Cấp độ | Điều có thể dựa vào | Điều không được suy ra |
| --- | --- | --- |
| **Java language** | `==` trên hai reference tới cùng object vẫn kiểm tra cùng identity; field access, method calls và monitor semantics của object vẫn đúng | Địa chỉ object sẽ không đổi |
| **JVM specification** | Objects/arrays được tạo và quản lý theo ngữ nghĩa heap; JVM có thể tự quản lý bộ nhớ và GC | Một thuật toán GC hoặc layout object duy nhất |
| **HotSpot collector** | Collector bảo toàn các references còn sống theo chính sách riêng khi copy/compact/move object | G1, ZGC, Shenandoah phải dùng cùng forwarding data structure hoặc thời điểm fix-up |
| **JIT/runtime** | Code đã tối ưu vẫn phải bảo toàn Java-visible behavior | Mọi local `Object` luôn nằm trong một stack slot vật lý |

Đặc tả JVM mô tả heap và cho phép bộ nhớ object được tự động reclaim. Nó **không** bắt buộc mọi implementation phải dùng **moving GC**. Một collector có thể không di chuyển một số hoặc tất cả object trong một chu kỳ; việc object vẫn ở một vị trí cũ không vi phạm Java.

Thêm nữa, có trường hợp compiler loại bỏ allocation vật lý bằng **escape analysis/scalar replacement** nếu vẫn giữ đúng hành vi quan sát được. Do đó chương trình Java cũng không được dùng kết quả chạy thành công để khẳng định “object này chắc chắn đã được copy từ địa chỉ X sang Y”.

## 3. GC roots: các điểm bắt đầu để tìm reference còn sống

Muốn biết object nào cần giữ và những reference nào phải theo dõi, collector bắt đầu từ một tập **GC roots** và các cấu trúc bổ sung do runtime quản lý.

Một số nguồn roots điển hình trên HotSpot:

- References trong **Java thread frames**, bao gồm local variables, operand-stack values và các vị trí trong register mà compiled code đang sử dụng.
- **Static references** của những class đã được load và vẫn thuộc phạm vi giữ sống cần thiết.
- **JNI local/global handles** và các runtime handles khác theo semantics tương ứng.
- Những references do chính VM/runtime giữ cho thread, class loader, monitor, code cache hoặc cấu trúc hỗ trợ.
- Các roots phục vụ GC phase cụ thể, ví dụ code roots và remembered-set-derived heap roots khi collection chỉ xử lý một phần heap.

**Root không có nghĩa object được giữ mãi:** khi stack frame rời khỏi hoặc reference không còn được coi là reachable, object có thể trở thành đối tượng để reclaim sau các điều kiện/reference processing thích hợp.

### Khác nhau giữa Java local và GC root thực tế

Một biến Java nhìn thấy trong source không nhất thiết vẫn là một **root sống** suốt cả lexical scope. Compiler/JIT có thể xác định local đã không còn được dùng và rút ngắn vùng liveness hợp lệ. Ngược lại, một reference có thể được giữ trong CPU register chứ không nằm nguyên trong memory slot của stack.

HotSpot dùng thông tin chính xác để nhận diện những vị trí chứa object references ở các điểm tương thích với GC, đặc biệt là **safepoints** và metadata liên quan đến compiled code.

**Phân biệt hai tên gần giống:**

- `StackMapTable` trong class file chủ yếu là metadata **bytecode verification**, giúp xác nhận kiểu stack/locals ở control-flow boundaries.
- **Oop maps**/GC maps trong runtime/JIT HotSpot giúp biết các vị trí chứa **object pointers** cần xử lý trong quá trình GC.
  
Chúng không phải một bảng chung có thể hoán đổi tùy ý; chỉ nhìn `javap -v` thấy `StackMapTable` không phải bằng chứng bạn đã xem được toàn bộ GC root map của JIT.

### Đồ thị reachable objects

```text
  GC roots
    |
    +----> object A -----> object C
    |          |
    |          +-------> object D
    |
    +----> object B -----> object C

Object C có thể được giữ bởi HAI đường,
nhưng vẫn chỉ là MỘT object logic.
```

Nếu C được di chuyển, cả những đường tham chiếu **có thể tiếp tục truy cập** C phải trỏ đúng C sau/qua quá trình relocation. Collector cũng phải duy trì thông tin để không copy C thành hai object Java khác identity do có hai roots cùng trỏ tới nó.

## 4. Moving/copying GC thường thực hiện các công việc nào?

Một mô hình giải thích **stop-the-world copying collector** đơn giản:

1. Xác định một tập object/heap regions cần collection; quyết định object nào còn sống theo thuật toán GC.
2. Từ các roots và edges thích hợp, gặp một reference tới object còn sống ở vùng cần evacuate.
3. Copy object sang vùng **to-space/destination** còn chỗ, hoặc xử lý ngoại lệ nếu không thể copy.
4. Ghi nhận ánh xạ **địa chỉ cũ → địa chỉ mới** qua forwarding information hoặc cấu trúc thích hợp.
5. Cập nhật root slots và field/array reference slots phù hợp để chúng trỏ tới object đích; tiếp tục quét reference fields của object vừa copy.
6. Khi relocation/fix-up đủ an toàn, giải phóng/tái sử dụng vùng cũ và cho application tiếp tục.

Ví dụ ký hiệu:

```text
from-space                       to-space

A@0x1000  -------- copy -------> A@0x9000
  ref X ----------- fix-up -----> A@0x9000
  ref Y ----------- fix-up -----> A@0x9000
  ref Z ----------- fix-up -----> A@0x9000

forward(A@0x1000) = A@0x9000

A chỉ là MỘT Java object về ngữ nghĩa;
không được xem A ở hai địa chỉ như hai object độc lập.
```

**Forwarding** giúp collector biết A đã được copy để lần gặp reference tiếp theo không tạo một bản Java object logic thứ hai. Khi collector gặp field/reference trỏ đến địa chỉ cũ, nó tìm địa chỉ mới và cập nhật/chuyển hướng phù hợp.

Câu “mọi reference được sửa ngay lập tức” chỉ đúng nếu đã mô tả **đầy đủ loại collector và giai đoạn**. Trong một collector đồng thời, điều kiện an toàn có thể được bảo đảm bằng **barriers**, metadata và fix-up theo pha, không phải bằng một thời điểm quét hết tất cả các slots.

### Không phải bước nào cũng “copy toàn bộ heap”

Một young collection có thể chỉ xử lý objects trong vùng trẻ; G1 mixed collection xử lý tập regions cụ thể, không phải mọi object trong heap. Collector còn có thể **mark/sweep**, **compact in place**, **copy/evacuate** hoặc kết hợp nhiều kỹ thuật qua các phases. Những object ở ngoài collection set có thể **không di chuyển**.

## 5. G1 trên HotSpot Java 17: evacuation và cập nhật references

G1 (Garbage-First) chia heap thành những **regions** và thu gom một **collection set (CSet)** trong các GC pauses. Đối với các regions được chọn, G1 thường **evacuate** các object còn sống sang regions đích.

G1 diễn giải “root” cho collection set rộng hơn chỉ GC roots truyền thống: một reference từ **bên ngoài CSet** vào **bên trong CSet** cũng quan trọng, vì object chứa reference có thể không nằm trong regions đang collection.

Ở mức khái niệm:

```text
Region P (ngoài CSet)           Region R (trong CSet)
+---------------------+         +------------------------+
| object Parent       |         | object Child @old      |
| childRef -----------+-------->| data, refs             |
+---------------------+         +------------------------+
           |
           | G1 quét root / remembered-set edges
           v
Region S (destination/to-space)
+-------------------------+
| object Child @new       |
| data, refs              |
+-------------------------+

Sau GC:
Parent.childRef -------------> Child @new
```

Trong implementation G1, forwarding information cho phép theo từ object cũ tới object được copy. Khi GC worker xử lý một reference slot vào CSet, nó có thể:

- Kiểm tra object đã có forwarding destination chưa.
- Nếu chưa, phối hợp để copy/claim object tới vị trí mới khi thích hợp.
- Đưa reference slot về destination tương ứng.
- Tiếp tục xử lý reference fields nằm trong object copy để mọi edges còn sống phù hợp được cập nhật.

Cần để ý **race giữa GC workers** trong cùng pause: hai GC workers có thể cùng phát hiện reference tới một object. Cơ chế claim/forwarding bảo đảm chỉ một **logical destination** được chấp nhận, không để hai tham chiếu của Java program trỏ tới hai object copy độc lập.

### Remembered sets và card marking

G1 không thể hiệu quả nếu ở mỗi young GC lại quét **toàn bộ old regions** chỉ để tìm các field trỏ vào young regions. Vì vậy nó dùng cơ chế tracking những **cross-region references**:

- **Write barriers/card marking** ghi nhận các thay đổi reference fields có thể làm xuất hiện cross-region edges cần biết.
- **Remembered sets** và các cấu trúc liên quan giúp xác định những vùng/slots cần quét trong collection của một số regions.
- Khi object được evacuate, tracking structures cũng cần duy trì tính đúng cho những references/regions mới.

**Một write barrier không phải bản thân GC copy object**. Nó là cơ chế hỗ trợ duy trì metadata/điều kiện để GC tìm edges cần thiết. Đọc “write barrier sửa reference” mà không biết đó là SATB marking, remembered-set tracking hay relocation phase là một cách diễn giải thiếu chính xác.

### Concurrent marking khác evacuation

G1 có **concurrent marking** để đánh giá liveness và chọn regions hiệu quả. Nhưng **evacuation of collection set** trong G1 Java 17 thường diễn ra trong **stop-the-world pauses**, khác với collectors thiết kế concurrent relocation. G1 có thể ghi log concurrent phases và evacuation pauses trong một GC cycle; đừng gộp tất cả thành “G1 di chuyển object đồng thời với Java threads”.

### Evacuation failure và objects không di chuyển

Nếu thiếu to-space, G1 có thể gặp **evacuation failure** và xử lý một phần objects theo chiến lược khác. Trong một số tình huống, object có thể được **self-forwarded/giữ ở vị trí cũ**. Ngoài ra, một số regions/objects không tham gia evacuation trong một pause.

Vì vậy không đúng khi khẳng định “G1 di chuyển mọi live object sau mỗi GC”. Cam kết cần giữ là **reference đúng và Java object identity đúng**, bất kể object có thực sự đổi vị trí hay không.

## 6. Concurrent moving collectors: vì sao reference có thể chưa được ghi lại ngay?

ZGC và Shenandoah theo đuổi mục tiêu giảm pause bằng cách thực hiện nhiều công việc GC **concurrent với application threads**. Với collector di chuyển object đồng thời, application có thể giữ một reference được đọc từ trước khi object hoàn tất relocation.

Để vẫn truy cập đúng object, collector dùng sự kết hợp của:

- **Forwarding/relocation metadata**: xác định object mới tương ứng với object cũ.
- **Load/read barriers**: xử lý reference khi application đọc/sử dụng, có thể kiểm tra trạng thái và chuyển hướng đến destination thích hợp.
- **Store/write barriers**: giữ invariant của các thuật toán concurrent marking/relocation khi application thay đổi reference graph.
- **Update/remap phases**: bảo đảm những reference cần thiết cuối cùng được đưa về trạng thái đúng theo chính sách collector.

### ZGC trong JDK 17

ZGC sử dụng các ý tưởng **colored pointers**, **load barriers** và **concurrent relocation/remapping** để quản lý references trong khi ứng dụng tiếp tục chạy phần lớn thời gian. Đây là mô tả **đặc thù implementation/version**, không phải định nghĩa chung của mọi JVM reference.

Không suy ra rằng một giá trị Java reference được lưu trong source có thể được convert thành một “colored pointer integer” rồi tự phân tích màu sắc. Những bit và encoding là cấu trúc mà runtime quản lý; thay đổi giữa các release/JVM là khả thi.

### Shenandoah trong JDK 17

Shenandoah có cơ chế **concurrent evacuation** và **barriers** để truy cập tới object đích và cập nhật references khi có object được di chuyển. Loại barrier cụ thể cùng chiến lược forwarding phụ thuộc Shenandoah mode/release; không dùng một sơ đồ riêng của ZGC để giải thích chắc chắn mọi implementation của Shenandoah.

### So sánh đúng cấp độ

| Khía cạnh | G1 trên HotSpot Java 17 | ZGC/Shenandoah trên JDK 17 phù hợp |
| --- | --- | --- |
| Phạm vi di chuyển | Collection set/regions được chọn | Các regions/objects theo chính sách collector |
| Evacuation/relocation | Phần chính trong STW collection pauses | Có những pha **concurrent với Java threads** |
| Cách giữ references hợp lệ | Scan/update slots, forwarding, remembered-set/barrier support | Forwarding + barriers/remapping theo từng collector |
| Object identity của Java | Không đổi | Không đổi |
| Địa chỉ có ổn định không? | **Không bảo đảm** | **Không bảo đảm** |
| Tất cả object luôn bị move? | Không | Không |
| Details bắt buộc bởi Java language? | Không | Không |

Khi nghiên cứu nội bộ GC, luôn chốt **JDK version/build/collector flags**. ZGC của JDK 17 khác các thế hệ ZGC sau này, và lựa chọn collector có thể thay đổi hành vi quan sát qua log, pause time, throughput và memory footprint.

## 7. Reference slot nằm ở đâu và GC cập nhật cái gì?

Một Java object có thể được tham chiếu qua nhiều loại “slot”:

| Nơi giữ reference | Ví dụ Java | Cơ chế ở mức HotSpot |
| --- | --- | --- |
| Local variable trong active method | `Node n = root;` | Root tại Java frame/compiled register nếu còn live; GC map giúp nhận diện |
| Operand stack của JVM frame | Giá trị receiver ngay trước `invokevirtual` | Runtime xử lý references trên frame/operand state |
| Static field | `static Node CACHE;` | Reference được giữ bởi class/runtime structures thích hợp |
| Instance field | `parent.child` | Reference trong heap object, có thể cần update nếu target move |
| Reference array element | `nodes[0]` | Slot nằm trong array object, có thể cần update |
| Collection graph | `list.get(0)`, `map.get(key)` | Thường là các field/array references của cấu trúc collection |
| JNI local/global reference | `jobject` handle | VM quản lý handle/reference đúng theo JNI contract |
| Compiled code roots | Oops embedded hoặc references trong compiled frames | JIT/VM duy trì metadata để GC có thể locate/update |

Với Java source, `list.get(0)` cho ra một reference; ở implementation, list có thể có backing array với reference slots. GC quan tâm tới **object graph và concrete slots/roots được VM biết**, không cần hiểu business meaning của tên `list`.

### Khi object chứa reference cũng được copy

Giả sử `Parent` và `Child` đều được evacuate. Collector cần đảm bảo trong **bản sao Parent** có child field trỏ tới **bản sao Child** thích hợp. Nếu child field vẫn chứa raw old address không hợp lệ sau khi vùng cũ được reclaim, Java behavior sẽ sai.

Mô hình:

```text
Trước:
Parent_old.child --> Child_old
root -----------> Parent_old

Sau:
root -----------> Parent_new
Parent_new.child --> Child_new

Forwarding:
Parent_old -> Parent_new
Child_old  -> Child_new
```

Về mặt Java, `root.child` vẫn là **chính Child đó**. Thứ tự copy và fix-up do collector điều phối; không nhất thiết phải copy Child ngay trước/đúng lúc Parent.

### Heap field là `final` có được GC “sửa reference” không?

Có sự khác nhau giữa **ứng dụng Java ghi lại một `final` field** và **VM cập nhật internal reference representation vì object relocation**. Quy tắc `final` của Java không ngăn GC duy trì reference hợp lệ khi target object move. Đó không phải một phép `putfield` nghiệp vụ thay đổi field từ Child A sang Child B. **Giá trị object logic được tham chiếu vẫn là Child A**.

## 8. Lý do `==`, `System.identityHashCode` và monitor vẫn hợp lệ

### Identity không phải địa chỉ

Giả sử:

```java
Node a = new Node();
Node b = a;
```

Đây là **fragment minh họa** trong một method; `Node` là class giả định.

Nếu a và b trỏ tới cùng một object, `a == b` là `true`. GC có thể đổi nơi lưu trữ của object nhưng không được làm Java quan sát nó như hai object khác nhau.

`System.identityHashCode(a)` cung cấp identity-based hash code theo contract của API. Giá trị cho **cùng object** không được biến đổi chỉ vì GC di chuyển nó; giá trị này **không phải raw address** và không được dùng làm địa chỉ/canonical identifier duy nhất toàn JVM. **Hai object khác nhau vẫn có thể trùng identity hash code**.

### Monitor và synchronized

Nếu thread giữ monitor của object qua `synchronized(lock)`, GC move của object không được làm monitor của nó “biến mất” hoặc khiến thread khác đồng bộ nhầm sang một object khác. Cách HotSpot lưu lock state/monitor/mark word là chi tiết triển khai tùy locking mode và JDK.

Không rút ra từ việc object header có thể dùng forwarding metadata rằng GC làm mất `hashCode`, lock state hoặc class pointer về mặt ngữ nghĩa. Collector và runtime phải duy trì những thuộc tính đó khi copy/relocate.

### Java object graph vẫn nhất quán

- Object reference trong array/field/list phải tiếp tục biểu diễn **cùng đích logic** nếu đích đó còn sống và ứng dụng có quyền truy cập.
- `IdentityHashMap` dùng reference identity semantics, không dùng địa chỉ thô bất biến mà chương trình được phép phụ thuộc.
- GC relocation **không** là một Java-level data race giữa threads; memory model/volatile/locks vẫn có semantics riêng.
- GC có thể là stop-the-world hoặc concurrent, nhưng tính đúng Java-visible behavior phải được bảo toàn.

## 9. Ví dụ Java 17 hoàn chỉnh: aliasing sống qua GC pressure

Tạo **`StableReferences.java`**:

```java
import java.util.ArrayList;
import java.util.IdentityHashMap;
import java.util.List;

public class StableReferences {
    static final class Node {
        final int id;
        Node next;

        Node(int id) {
            this.id = id;
        }
    }

    // Giữ một allocation mới reachable để giảm khả năng bị loại bỏ
    // chỉ bởi optimization. Đây không phải bằng chứng object đã move.
    static volatile Object allocationSink;

    public static void main(String[] args) {
        Node first = new Node(7);
        Node second = new Node(9);
        first.next = second;

        Node alias = first;
        Node[] array = {first};
        List<Node> list = new ArrayList<>();
        list.add(first);

        IdentityHashMap<Node, String> names = new IdentityHashMap<>();
        names.put(first, "first");

        int identityBefore = System.identityHashCode(first);

        for (int i = 0; i < 400; i++) {
            allocationSink = new byte[64 * 1024];
        }

        System.out.println("aliasSame=" + (first == alias));
        System.out.println("arraySame=" + (first == array[0]));
        System.out.println("listSame=" + (first == list.get(0)));
        System.out.println("linkedId=" + first.next.id);
        System.out.println("mapValue=" + names.get(alias));
        System.out.println("stableIdentityHash="
                + (identityBefore == System.identityHashCode(first)));
    }
}
```

Biên dịch/chạy bằng Java 17+:

```bash
javac --release 17 StableReferences.java
java StableReferences
```

**Stdout của chương trình**, không phụ thuộc có xảy ra moving GC hay không:

```text
aliasSame=true
arraySame=true
listSame=true
linkedId=9
mapValue=first
stableIdentityHash=true
```

Điều được chương trình kiểm tra là **Java reference semantics**: aliasing, reference fields/arrays/collections và identity hash code không được hỏng. Nó **không chứng minh** một object đã di chuyển, vì JVM có thể không GC, chỉ GC vùng khác, giữ object ở chỗ cũ hoặc tối ưu một số allocations.

### Tạo áp lực heap và bật GC log có kiểm soát

Có thể chạy lại trên một HotSpot hỗ trợ G1:

```bash
java -Xms16m -Xmx32m -XX:+UseG1GC -Xlog:gc StableReferences
```

**GC log, số lần GC và thời điểm pause không cố định** theo OS/JVM/build. Nếu collector thực hiện young evacuation, log sẽ cung cấp thông tin về collection; nhưng ngay cả khi log báo GC, **không thể suy ra từ output một object cụ thể đã move**. Số byte tạo ra trong vòng lặp, khả năng optimization và chính sách region allocation đều ảnh hưởng thực tế.

Với collector G1, lệnh:

```bash
java -Xms16m -Xmx32m -XX:+UseG1GC -Xlog:gc*,gc+phases=debug StableReferences
```

có thể cho thêm phase logging khi build hỗ trợ lựa chọn log tags. Không dùng một mốc BCI, số GC hoặc địa chỉ tưởng tượng trong ví dụ làm assertion test.

### Vì sao dùng `IdentityHashMap`?

`IdentityHashMap` so key bằng `==` thay vì `equals`, hữu ích để chứng minh Java identity semantics chứ không chứng minh pointer bits. Nếu object được dời, map vẫn phải lấy đúng value cho key cùng identity. **Không suy ra internals của `IdentityHashMap` lưu raw address**.

## 10. Khi có weak/soft/phantom references: relocation khác clearing

`java.lang.ref.Reference` tạo thêm quy tắc về reachability:

- **Strong references** thông thường có thể giữ object reachable.
- **SoftReference** có chính sách clearing liên quan memory sensitivity, không có lịch định thời xác định.
- **WeakReference** không giữ referent sống như strong reference; GC có thể clear khi đối tượng đã weakly reachable theo điều kiện thích hợp.
- **PhantomReference** có cơ chế được dùng để theo dõi hậu xử lý và cleanup; `get()` luôn trả `null`; dùng `ReferenceQueue` phù hợp.

Hai hành động **khác nhau**:

1. **Move live referent:** object vẫn còn sống, collector cần bảo đảm reference tới object vẫn hợp lệ, có thể remap/forward.
2. **Clear referent của `Reference` object:** khi reachability và reference processing yêu cầu, field tham chiếu logic được chuyển thành null theo contract, để Java có thể quan sát `weak.get() == null`.

Không được đọc `WeakReference.get() == null` rồi kết luận “GC di chuyển object nên pointer bị thay thành null”. Weak-reference clearing là **quy tắc reachability**, không phải lỗi relocation.

### Ví dụ Java 17 kiểm tra strong reachability mà không dựa vào thời điểm GC

Tạo **`WeakReferenceSemantics.java`**:

```java
import java.lang.ref.Reference;
import java.lang.ref.WeakReference;

public class WeakReferenceSemantics {
    public static void main(String[] args) {
        Object strong = new Object();
        WeakReference<Object> weak = new WeakReference<>(strong);

        System.out.println("getBefore=" + (weak.get() != null));

        // Giữ strong reachable tới đúng điểm cuối được chỉ định.
        Reference.reachabilityFence(strong);
    }
}
```

```bash
javac --release 17 WeakReferenceSemantics.java
java WeakReferenceSemantics
```

**Stdout xác định:**

```text
getBefore=true
```

`Reference.reachabilityFence(strong)` cho chương trình chỉ định một thời điểm mà `strong` phải được xem là strongly reachable. Ví dụ cố ý **không** gọi `System.gc()` hoặc in `weak.get()` sau khi đánh mất strong reference, vì **khi nào GC chạy/clear weak reference là không xác định**.

### Vùng reference được collector xử lý đặc biệt

Một collector có thể có **reference processing phases** cho `java.lang.ref` references. Ở G1, weak/soft/phantom reference handling là công việc phân biệt với copy/update ordinary strong references; GC log cũng có thể thể hiện riêng những phases. Không dùng thuật ngữ “reference processing” chung chung để khẳng định mọi update của oop khi evacuation đều có cùng quy tắc clearing.

## 11. JNI handles, native pointer và việc Java object có thể di chuyển

JNI là một nơi dễ tạo lỗi nghiêm trọng nếu lập trình viên C/C++ giữ địa chỉ theo giả định sai.

### `jobject` không phải raw stable object address

Theo cách dùng JNI chuẩn, object được truyền qua **JNI references/handles**. VM quản lý handles để collector có thể xử lý relocations thích hợp. Caller native dùng `jobject` theo **JNI lifetime rules**, không tự suy thành địa chỉ object nguyên thủy ổn định.

- **JNI local reference** thường hợp lệ trong phạm vi native call/frame tương ứng, có thể được VM giải phóng khi trả về theo contract.
- **JNI global reference** tồn tại tới khi native code giải phóng bằng API thích hợp; giữ global reference quá lâu cũng có thể giữ object sống và gây retention.
- **Weak global reference** có semantics khác strong global reference; có thể trở nên không còn referent nếu GC clear.
- Nếu lưu trực tiếp memory address của một Java object sang `uintptr_t` hay `long`, JVM **không hứa** cập nhật số nguyên ấy khi GC move object. Đó không phải GC-tracked reference slot hợp lệ.

### `GetPrimitiveArrayCritical` và việc pin/copy

JNI API cung cấp cách lấy pointer tới nội dung primitive array trong một khoảng sử dụng theo contract cụ thể. JVM có thể sử dụng **pinning**, **copy** hoặc chiến lược thích hợp tùy runtime/API. Native code phải tuân thủ ràng buộc critical region và gọi hàm **Release** tương ứng đúng lúc.

Không suy rằng vì có API `GetPrimitiveArrayCritical` nên **mọi object Java khác** sẽ bị pin, hoặc địa chỉ trả về vẫn sử dụng hợp lệ sau khi release. API JNI không phải cách tổng quát để lấy “địa chỉ Java object vĩnh viễn”.

### Direct buffers khác heap object

`ByteBuffer.allocateDirect` sử dụng backing memory với ngữ nghĩa direct buffer; Java object wrapper vẫn được GC quản lý và có thể di chuyển. Backing memory nằm ngoài Java heap theo cơ chế implementation; pointer native của backing region có những lifetime rules khác Java object reference.

Điều này giải thích vì sao một native buffer address ổn định trong phạm vi API cụ thể **không** chứng minh địa chỉ của mọi Java object ổn định.

## 12. Compressed oops: reference Java không nhất thiết là pointer machine-width

Trong nhiều cấu hình 64-bit HotSpot, reference đến Java heap objects có thể được lưu ở dạng **compressed ordinary object pointers (compressed oops)** nhằm giảm dung lượng memory dùng cho object fields/arrays. JVM decode/encode thành địa chỉ sử dụng ở implementation.

Điều cần hiểu:

- Java `Object` reference **không có primitive type size được JLS quy định** là 32 hay 64 bit.
- Một số HotSpot heap configurations dùng compressed oops, số khác không; encoding có thể sử dụng base/shift và các phương án tùy runtime.
- Khi object move, collector/JIT phải bảo đảm reference representation dù compressed hay không vẫn dẫn tới object logic đúng.
- `System.identityHashCode(obj)` không cho raw object address và không dùng để suy compressed-oop bits.
- Thông tin compressed oops không thể thay thế GC root maps và forwarding/relocation logic.

Có thể quan sát một số flags trên HotSpot:

```bash
java -XX:+PrintFlagsFinal -version
```

Tìm `UseCompressedOops` và các flags liên quan trong output của build, nhưng đừng suy ra **memory layout chính xác** chỉ từ một flag. Chi tiết JDK/vendor/GC config còn quyết định object alignment và cách giải mã.

## 13. Safepoints, barriers và đồng bộ giữa GC/mutator

### Stop-the-world

Trong stop-the-world GC phases, application threads được đưa tới trạng thái an toàn để collector duyệt, relocate và cập nhật cần thiết mà không để mutators đồng thời thay đổi đồ thị heap theo cách không được kiểm soát. Cách HotSpot phối hợp safepoints/handshakes là chi tiết implementation.

Một lời gọi `synchronized` **không phải** cơ chế application cần thêm để làm GC update references an toàn. GC/VM tự đảm nhận sự nhất quán nội bộ.

### Concurrent

Với concurrent collector, application thread là **mutator** vì nó có thể đọc/ghi fields, tạo object và thay đổi reference graph trong lúc GC chạy. Những barriers và phase invariants đảm bảo không nhìn thấy reference sai.

Ví dụ mô hình:

```text
Mutator đọc field -> read/load barrier -> effective target object
Mutator ghi field -> write barrier -> tracking/marking/remembered metadata
GC relocated object -> forwarding/remapping -> references remain valid
```

Tuy nhiên, đây chỉ là **sơ đồ cấp cao**. G1 write barriers phục vụ remembered sets/marking, không được lấy làm bằng chứng G1 đang thực hiện concurrent evacuation. ZGC và Shenandoah có barrier implementations khác, không nên so sánh từng instruction bằng nhau.

### Barriers của GC khác `volatile` và memory fences của Java Memory Model

- **GC barrier:** runtime instrumentation để GC duy trì invariants (marking, remembered sets, remapping...).
- **`volatile`/synchronization/JMM:** bảo đảm visibility/ordering/happens-before cho chương trình Java.
- Một compiler/JIT có thể cài đặt cả hai loại với các thao tác máy khác nhau hoặc kết hợp tối ưu, nhưng **ngữ nghĩa và mục đích không đồng nhất**.
- GC reference update **không** thay thế nhu cầu đồng bộ ứng dụng khi nhiều threads cùng sửa một mutable object.

## 14. Không phải mọi object bắt buộc move: “pinned”, “humongous”, evacuation failure

Một số trường hợp không thể suy ra relocation:

1. **Vùng không nằm trong collection set**: object có thể không được copy.
2. **GC không xảy ra**: tạo áp lực heap hoặc gọi `System.gc()` không phải bằng chứng chắc chắn đối tượng đã move.
3. **Large/humongous objects**: một số collector có chính sách đặc biệt với objects chiếm nhiều regions; relocation có thể không theo đường evacuation thông thường.
4. **Evacuation failure/to-space exhaustion**: collector có thể giữ một số objects ở nơi cũ và xử lý fallbacks.
5. **Native/JNI critical regions hoặc pinning**: có thể ảnh hưởng khả năng/mốc thời gian relocate những objects liên quan theo API/collector.
6. **Non-moving phases/collectors**: mark-sweep không nhất thiết có bước relocation như copying GC.

Mục đích của relocation thường gồm thu gom vùng nhớ hiệu quả, giảm fragmentation, hỗ trợ bump-pointer allocation và region-based management, nhưng collector còn cân bằng throughput, pause-time và CPU/memory overhead.

Một object “không di chuyển trong lần GC quan sát được” **không** tạo hợp đồng địa chỉ cố định cho lần sau.

## 15. Làm sao biết GC đã move một object cụ thể?

Từ Java portable code, **không có API chuẩn trả raw heap address ổn định để so sánh trước/sau GC**. Vì vậy:

- `System.identityHashCode(obj)` chỉ đo identity-based hash code, không đo địa chỉ.
- `obj.toString()` theo `Object` thường chứa phần hash code dạng hex, cũng **không** phải heap address.
- `Unsafe`/JOL/debugger nội bộ có thể cho thông tin implementation-specific, nhưng reference encoding, GC timing và cách đọc memory rất dễ làm kết quả sai. Không sử dụng raw addresses để làm logic ứng dụng.
- GC logs cho biết các hoạt động GC phases/regions/bytes tùy log level, thường **không** liệt kê mọi lần relocate từng object theo một identifier ổn định.
- Heap dump/diagnostic tools có thể biểu diễn object IDs hoặc locations phục vụ snapshot, nhưng IDs/address được in không phải contract identity của Java giữa nhiều snapshots.

Nếu mục tiêu chỉ là bảo đảm chương trình không hỏng sau GC, test nên kiểm tra **nội dung, aliasing và object identity semantics**. Nếu mục tiêu là nghiên cứu collector internals, dùng **build/diagnostics được khóa phiên bản**, GC log/JFR/SA/JVM debug instrumentation theo khả năng của môi trường, đồng thời nêu giới hạn quan sát.

### Gợi ý kiểm tra G1 phases

Với JVM test đang chạy đủ lâu:

```bash
java -XX:+UseG1GC -Xlog:gc*,gc+phases=debug -jar app.jar
```

`app.jar` là tên **ứng dụng mẫu** phải thực sự tồn tại, không phải file được tạo trong bài. Trong log, tìm các dòng về **Evacuate Collection Set**, root scanning, object copy/evacuation, reference processing, pause time. Tên phase/chú thích có thể đổi giữa các versions/GC log levels.

Cùng lúc, có thể kiểm tra:

```bash
jcmd <PID> GC.heap_info
jcmd <PID> VM.flags
```

`<PID>` là chỗ đứng cho process ID thực. Các lệnh `jcmd` không trả danh sách raw object references đã được fix-up, nhưng giúp xác định collector, heap settings và tình trạng runtime. Không lấy sample logs của môi trường khác làm bằng chứng cho process hiện tại.

## 16. Một số lỗi debug phổ biến

| Suy luận sai | Điều đúng |
| --- | --- |
| “Reference Java là địa chỉ object luôn bất biến” | Java bảo đảm semantics tham chiếu, không bảo đảm physical address |
| “GC move object sẽ làm `a == b` sai” | Collector bảo toàn aliasing/identity semantics |
| “Reference ở local biến mất khi object move” | VM cập nhật/chuyển hướng roots còn sống theo cơ chế GC |
| “Collector luôn quét từng heap field sau mỗi minor GC” | Region/remembered-set/root discovery giúp tránh quét toàn bộ không cần thiết |
| “Forwarding pointer là một Java field người dùng nhìn thấy” | Đây là internal GC/VM metadata, không phải public Java API |
| “G1 evacuate đồng thời giống ZGC” | G1 Java 17 chủ yếu evacuate trong STW pauses; concurrent marking là giai đoạn khác |
| “Mọi Java collector dùng cùng một load barrier” | Barrier strategy là implementation-specific |
| “Write barrier nghĩa là Java `volatile`” | GC barrier và JMM synchronization khác mục đích |
| “`final Node child` ngăn GC sửa pointer bits” | `final` bảo vệ ngữ nghĩa chương trình; GC vẫn duy trì internal representation |
| “`System.identityHashCode` là memory address” | Là identity-based hash, không phải address; có thể collision |
| “`WeakReference.get() == null` chứng minh GC đã move object” | Đó là reachability/reference clearing, không phải relocation |
| “Đã có `jobject` thì native code giữ raw pointer mãi mãi được” | JNI handles có lifetime rules; raw object address không ổn định |
| “`System.gc()` chắc chắn chạy moving GC” | Chỉ là yêu cầu/hint; không bảo đảm di chuyển object cụ thể |
| “JVM GC tự giải quyết mọi data race” | GC giữ internal memory safe; app vẫn cần proper synchronization |
| “Array/list giữ object theo đúng physical address của lúc thêm” | Chúng giữ references có semantics được JVM duy trì |
| “GC log có pause nghĩa tất cả live objects đã move” | Collection scope có thể chỉ là một số regions; nhiều objects không move |

## 17. Quy trình phân tích vấn đề liên quan tới object relocation

**Bước 1 — Chốt implementation.** Ghi JVM vendor/build/version, collector đang dùng, heap flags và nền tảng. Tránh trộn G1 code từ JDK mới với ZGC của JDK 17.

**Bước 2 — Xác định dấu hiệu.** Đây là lỗi `ClassCastException`, `NullPointerException`, lỗi JNI native crash, heap corruption, aliasing giả định sai hay object được GC clear vì weak reference? Các lỗi có nguyên nhân khác nhau.

**Bước 3 — Kiểm tra Java-visible contract.** Xác nhận cùng object bằng `==`, nội dung fields, đồng bộ Java đúng và lifetime của reference. Đừng dùng identity hash làm raw pointer.

**Bước 4 — Xác định GC roots.** Có reference còn sống từ stack, static fields, heap objects, JNI handles hay không? Một local đã hết liveness không tự giữ object suốt lexical scope.

**Bước 5 — Hiểu collector phase.** G1 evacuation? Concurrent marking? ZGC/Shenandoah remapping? Một phase không có nghĩa mọi object bị di chuyển.

**Bước 6 — Đối chiếu reference category.** Strong, weak/soft/phantom, JNI local/global/weak global, direct/native memory, pinned primitive array đều có semantics khác nhau.

**Bước 7 — Với JNI/Unsafe/agent, kiểm tra lifetime và tính hợp lệ.** Không lưu raw object address ngoài hợp đồng VM; không tự chỉnh class/object headers, compressed oop bits hoặc forwarding metadata.

**Bước 8 — Sử dụng diagnostics có kiểm soát.** `-Xlog:gc*`, JFR/JVM diagnostics khi phù hợp, heap dump/JOL/SA nếu đang nghiên cứu implementation; tránh ép GC trong production chỉ để tạo một “địa chỉ trước/sau”.

**Bước 9 — Viết regression tests theo kết quả Java.** Kiểm tra object graph, aliasing, identity maps, collection contents, concurrency invariants thay vì kiểm tra offset/address ngẫu nhiên.

**Bước 10 — Kết luận đúng độ chắc chắn.** “References vẫn đúng sau GC” có thể xác nhận bằng Java semantics; “object A thật sự đổi từ 0x... sang 0x...” cần bằng chứng implementation-level phù hợp.

## 18. Câu hỏi tự kiểm tra

**Câu 1:** `Node a = new Node(); Node b = a;`, GC copy object sang vùng khác. Biểu thức `a == b` có được phép đổi thành `false`?

**Không.** Hai references vẫn trỏ tới cùng một logical object.

**Câu 2:** Một field `parent.child` trỏ tới Child vừa được evacuate. Collector cần bảo đảm điều gì?

**Đọc field vẫn lấy đúng Child**, bằng update reference slot hoặc cơ chế chuyển hướng/remapping thích hợp; không để application thấy stale raw address không hợp lệ.

**Câu 3:** Forwarding information để làm gì khi nhiều roots cùng trỏ đến một object?

Để nhận ra object **đã được copy** và cho các paths cùng tìm tới destination hợp lệ, thay vì sinh nhiều logical copies độc lập.

**Câu 4:** G1 young GC cần quét toàn bộ old heap mới phát hiện old-to-young edges?

Không nhất thiết. G1 dùng remembered sets, card marking và các cơ chế tracking roots phù hợp.

**Câu 5:** ZGC có thể sửa reference vào lúc application đọc nó không?

Có thể. ZGC dùng load barriers và relocation/remapping mechanisms; không được suy rằng tất cả slots luôn được eagerly rewritten cùng một lần STW.

**Câu 6:** `System.identityHashCode(obj)` đổi sau relocation?

Không vì riêng relocation. Nó là identity-based hash, không phải raw address.

**Câu 7:** `WeakReference.get() == null` cho biết object đã move hay đã bị clearing?

Kết quả null có thể do **weak reference clearing** theo reachability rules; không phải chỉ báo relocation.

**Câu 8:** Một biến Java source còn trong scope có chắc chắn giữ object làm GC root không?

Không. Liveness có thể kết thúc trước scope end. Dùng `Reference.reachabilityFence` khi thật sự cần duy trì strong reachability tới một điểm nhất định.

**Câu 9:** Đã nhận `jobject` qua JNI, có thể cast sang địa chỉ native và cache suốt quá trình không?

Không. Dùng JNI references/handles theo lifetime contract; JVM không hứa update một raw integer address do native code tự lưu.

**Câu 10:** Một GC log có dòng “Evacuate Collection Set” có chứng minh object cụ thể trong biến `first` đã chuyển địa chỉ không?

Không. Log phản ánh GC phase, không định danh chắc chắn object cụ thể và không cho raw address trước/sau.

## Nguồn gốc và tài liệu tra cứu

- [JVMS Java SE 17 `2.5.3 — Heap](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5.3): runtime heap và quản lý objects.
- [JVMS Java SE 17 `2.6 — Frames](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.6): JVM frame, local variables, operand stack và references.
- [Oracle Java SE 17 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html): root processing, evacuation, remembered sets và các tình huống failure.
- [OpenJDK source — G1ParScanThreadState (reference evacuation/update)](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/gc/g1/g1ParScanThreadState.cpp): ví dụ rõ về forwarding và cập nhật reference slot, **lưu ý link nhánh main không nhất thiết trùng JDK 17**.
- [JEP 333 — ZGC](https://openjdk.org/jeps/333): mục tiêu và ý tưởng concurrent GC, colored pointers/load barriers.
- [JEP 189 — Shenandoah](https://openjdk.org/jeps/189): concurrent evacuation của collector.
- [Java SE 17 `Object`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html) và [`System.identityHashCode`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#identityHashCode(java.lang.Object)): object identity và identity-based hash.
- [Java SE 17 `IdentityHashMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/IdentityHashMap.html): key comparison theo `==`.
- [Java SE 17 `Reference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/Reference.html) và [`WeakReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): reachability, clearing và `reachabilityFence`.
- [JNI Specification Java SE 17 — JNI Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): local/global references, weak globals, critical array access.
- [Java SE 17 `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): direct buffers và heap buffers.
- [Java SE 17 `java` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html), [`jcmd`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): collector flags, unified GC logging và VM diagnostics.

**Ghi nhớ:** khi HotSpot di chuyển object, **Java reference semantics và object identity phải không đổi**. G1 thường cập nhật roots/field slots trong evacuation pauses với forwarding; collector đồng thời có thể duy trì correctness qua **barriers và remapping** ở các thời điểm khác nhau. Java code nên tin vào **object identity, reachability và chuẩn đồng bộ**, không dựa vào địa chỉ thô, số identity hash, hay giả định mọi lần GC đều di chuyển mọi object.
