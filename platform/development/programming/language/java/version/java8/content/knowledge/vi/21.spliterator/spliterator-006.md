# Spliterator: SIZED, SUBSIZED, IMMUTABLE và CONCURRENT

`Spliterator<T>` là giao diện dùng để **duyệt** và **chia nguồn phần tử thành các phần** (qua `trySplit()`), giúp những thư viện như Java Stream tổ chức cả xử lý tuần tự lẫn song song. Từ Java 8 đến Java hiện hành, giao diện này có một bộ cờ (*characteristics*) mô tả những cam kết về **kích thước**, **khả năng chia nhỏ**, **tính ổn định của nguồn** và **việc thay đổi nguồn đồng thời**.

Bốn cờ cần hiểu đúng:

- `SIZED`: biết **chính xác số phần tử** trong phạm vi điều kiện của API, trước khi duyệt/chia.
- `SUBSIZED`: các Spliterator con do `trySplit()` tạo ra đều có thông tin kích thước chính xác.
- `IMMUTABLE`: **nguồn phần tử đang được duyệt** không bị thay đổi cấu trúc trong quá trình duyệt.
- `CONCURRENT`: nguồn có thể được thay đổi cấu trúc **an toàn bởi nhiều luồng**, theo chính sách nhất quán mà nguồn công bố.

Đây là bốn cờ của **Spliterator**, không phải bốn chế độ tự động kích hoạt của `parallelStream()`. Khai báo sai cờ khi tự triển khai Spliterator có thể khiến những thuật toán dựa vào cờ đó đưa ra quyết định sai hoặc kết quả không được API bảo đảm.

## 1. Đọc cờ và kích thước từ API

Các phương thức thường dùng:

~~~java
int flags = spliterator.characteristics();

boolean sized =
        spliterator.hasCharacteristics(Spliterator.SIZED);

boolean sizedAndSubsized =
        spliterator.hasCharacteristics(
                Spliterator.SIZED | Spliterator.SUBSIZED);

long estimate = spliterator.estimateSize();
long exactOrMinusOne = spliterator.getExactSizeIfKnown();
~~~

Đây là **mảnh code minh họa**, giả sử `spliterator` đã có kiểu `Spliterator<?>` và import `java.util.Spliterator`.

- `characteristics()` trả một **bitmask**. Các giá trị hằng của `Spliterator` được gộp bằng toán tử bitwise OR `|`.
- `hasCharacteristics(mask)` trả true khi đối tượng có **đủ tất cả bit** được yêu cầu. Vì vậy `hasCharacteristics(SIZED | SUBSIZED)` là kiểm tra đồng thời hai cờ.
- `estimateSize()` trả số lượng ước lượng; nếu kích thước không biết hoặc quá tốn kém để tính, nó có thể trả `Long.MAX_VALUE`.
- `getExactSizeIfKnown()` mặc định trả `estimateSize()` nếu có `SIZED`, và trả `-1` nếu không có `SIZED`. Giá trị `-1` **không có nghĩa nguồn trống**.
- Một Spliterator có thể có nhiều cờ, ví dụ `ORDERED` đi cùng `SIZED` và `SUBSIZED`. Cờ không liệt kê ở đây không có nghĩa bị cấm; bài này chỉ tập trung vào bốn cờ đã nêu.

**Lưu ý quan trọng:** Spliterator dùng để **tiêu thụ nguồn một lần**, không phải một collection có thể đọc lại tùy ý. `tryAdvance()` và `forEachRemaining()` tiêu thụ phần tử; `trySplit()` tách một phần nguồn sang Spliterator khác. Nên kiểm tra kích thước và cờ tại thời điểm phù hợp, trước khi bắt đầu duyệt nếu muốn dùng chúng làm tiền điều kiện.

## 2. SIZED: biết kích thước ban đầu, không chỉ “ước lượng có vẻ đúng”

`Spliterator.SIZED` nói rằng giá trị `estimateSize()` trước khi Spliterator được duyệt hoặc tách đại diện cho một **kích thước hữu hạn và chính xác** của những phần tử sẽ được gặp khi duyệt hết, **nếu nguồn không bị thay đổi cấu trúc**.

Ví dụ một `ArrayList` chứa bốn phần tử: Spliterator trên danh sách thường có `SIZED`; `getExactSizeIfKnown()` lúc đầu trả 4. Với một nguồn động không biết số phần tử sẽ phát sinh, không được khai báo `SIZED` chỉ vì đã tính được một con số ước lượng.

Phân biệt:

~~~text
SIZED:
  "Tôi biết chính xác số phần tử mà phép duyệt đầy đủ sẽ gặp,
   trong điều kiện nguồn không bị thay đổi cấu trúc."

Không có SIZED:
  "Tôi có thể ước lượng, nhưng không cam kết đếm chính xác."
~~~

### 2.1. Điều gì được và không được bảo đảm?

- `SIZED` **không tự nói gì** về thứ tự phần tử, khả năng sửa đổi nguồn hay thread-safety.
- `SIZED` **không đồng nghĩa** với `SUBSIZED`; phần nguồn ban đầu có thể biết số lượng chính xác nhưng các nhánh tách không thể biết chính xác.
- Các bảo đảm về `estimateSize()` còn phụ thuộc việc Spliterator **đã duyệt một phần hoặc chia nhỏ hay chưa**. Với `SIZED` nhưng không `SUBSIZED`, không tự giả định mọi nhánh sau `trySplit()` cũng chính xác.
- Nếu phần tử nguồn bị thay đổi cấu trúc trái với hợp đồng, việc dựa vào kích thước ban đầu là không an toàn.
- Không suy ra `SIZED` bắt buộc phải nhanh hay cho phép thay đổi collection trong khi duyệt. Nó là **cam kết về số phần tử**, không phải cam kết hiệu năng hoặc đồng bộ hóa.

### 2.2. Liên hệ với `Stream.count()`

Một Stream có nguồn `SIZED` và các bước pipeline không thay đổi số lượng có thể được tối ưu để tính `count()` **mà không chạy mọi thao tác trung gian**. Ví dụ, đừng dùng `peek` hoặc `map` để ghi log/bộ đếm rồi giả định chúng sẽ luôn được gọi khi terminal operation là `count()`.

~~~java
long count = java.util.List.of(10, 20, 30).stream()
        .peek(x -> System.out.println("seen " + x))
        .count();
~~~

Đây là đoạn đặt trong một phương thức. `count` trả `3`; **không có bảo đảm ba dòng `seen` sẽ được in**. Các tối ưu hóa của Stream được phép bỏ qua callback không ảnh hưởng đến kết quả. Trái lại, sau một phép `filter`, số phần tử thường không còn biết chính xác từ kích thước nguồn; trong triển khai JDK thông dụng, Spliterator của pipeline lọc không báo `SIZED`.

**Đừng xem các đặc tính của Spliterator nguồn và Spliterator sau mọi intermediate operation là giống hệt nhau.** Cờ là mô tả về từng Spliterator cụ thể tại thời điểm sử dụng.

## 3. SUBSIZED: kích thước chính xác được bảo toàn khi chia

`Spliterator.SUBSIZED` cam kết **mọi Spliterator sinh ra từ `trySplit()`**, bao gồm con trực tiếp và con ở các mức sâu hơn, cũng báo `SIZED` và `SUBSIZED`. Vì vậy:

- **Có `SUBSIZED` thì phải có `SIZED`**. Một implementation báo `SUBSIZED` nhưng không báo `SIZED` là **không nhất quán**.
- **Có `SIZED` không bắt buộc có `SUBSIZED`**. Một cấu trúc có thể biết tổng số phần tử nhưng không biết chính xác số phần tử trong mỗi nhánh sau khi chia.
- Với nguồn ổn định, trước khi duyệt một phần, khi Spliterator `SUBSIZED` tách thành nhánh con và phần còn lại, tổng `estimateSize()` của chúng **bằng kích thước trước khi tách**.

Ví dụ:

~~~text
Ban đầu:  [10, 20, 30, 40]  (SIZED + SUBSIZED), size = 4
trySplit:
  nhánh tiền tố: [10, 20]    size = 2
  phần còn lại: [30, 40]     size = 2
  tổng: 2 + 2 = 4
~~~

Đây là **mô hình minh họa một lần chia**, không phải cam kết mọi nguồn và phiên bản JDK sẽ luôn chia chính giữa. Với Spliterator `ORDERED`, nếu `trySplit()` trả một Spliterator khác null, nó phải đại diện cho một **tiền tố** phần tử của Spliterator đang được chia.

### 3.1. Vì sao SUBSIZED hữu ích?

Khi triển khai xử lý song song, thông tin kích thước chính xác ở **từng nhánh** giúp ước lượng và phân chia công việc, phân bổ vùng đệm hoặc vị trí ghi kết quả theo cách phù hợp. Nhưng `SUBSIZED` **không bảo đảm**:

- Các phần được chia có kích thước bằng nhau hay sẽ đủ lớn để bù chi phí parallel.
- Công việc trên mỗi phần tử có chi phí giống nhau.
- Tự động đạt tăng tốc khi chuyển sang `parallel()`.

Một Spliterator phân chia mất cân bằng có thể vẫn không đạt hiệu năng tốt dù có `SUBSIZED`. Hãy đo đạc trên dữ liệu thực tế thay vì suy ra tốc độ từ tên cờ.

### 3.2. SIZED nhưng không SUBSIZED

`HashSet` trong triển khai JDK phổ biến có Spliterator gốc báo `SIZED` nhưng không báo `SUBSIZED`: biết tổng phần tử của set, nhưng không cam kết mọi nhánh tách đều biết kích thước chính xác. Tương tự, API Java mô tả các cấu trúc cây có thể biết kích thước toàn cây mà không biết chính xác kích thước từng cây con.

**Không dùng `getExactSizeIfKnown() == -1` ở một Spliterator con làm bằng chứng nó rỗng.** Muốn biết phần tử thực sự, phải duyệt/đếm theo cách phù hợp.

## 4. IMMUTABLE: nguồn duyệt ổn định, không phải mọi object bất biến

`Spliterator.IMMUTABLE` mô tả nguồn phần tử của Spliterator **không thể bị thay đổi cấu trúc trong lúc duyệt**, nghĩa là những phần tử trong nguồn duyệt không bị thêm, bỏ hoặc thay thế trong thời gian đó.

Điểm rất dễ nhầm:

- **Không có nghĩa mỗi object `T` đều là immutable**. Một Spliterator duyệt các object mutable có thể có `IMMUTABLE` nếu nguồn duyệt ổn định.
- **Không có nghĩa mọi collection sở hữu dữ liệu đều không thể sửa**. Có collection sửa được, nhưng Spliterator duyệt **một snapshot** không đổi.
- **Không có nghĩa chính Spliterator an toàn để nhiều thread cùng gọi `tryAdvance()`**.
- **Không có nghĩa `SIZED` hay `SUBSIZED` luôn có mặt**; bốn cờ mô tả các khía cạnh khác nhau.

### 4.1. Ví dụ CopyOnWriteArrayList

`CopyOnWriteArrayList` là collection hỗ trợ nhiều luồng. Nhưng Spliterator của nó làm việc với **snapshot** của một mảng dữ liệu tại thời điểm tạo Spliterator; snapshot đó không chịu ảnh hưởng của việc thêm/xóa sau này và báo `IMMUTABLE`.

~~~java
java.util.concurrent.CopyOnWriteArrayList<String> list =
        new java.util.concurrent.CopyOnWriteArrayList<>(
                java.util.List.of("A", "B"));

java.util.Spliterator<String> snapshot = list.spliterator();
list.add("C");

java.util.List<String> seen = new java.util.ArrayList<>();
snapshot.forEachRemaining(seen::add);

System.out.println(seen); // [A, B]
System.out.println(list); // [A, B, C]
~~~

Mảnh code trên chạy được khi đặt trong `main` (JDK 17+). Điều quan trọng: **collection vẫn đổi được**, nhưng nguồn dữ liệu *đã chụp* để Spliterator duyệt không đổi. Đây là lý do Spliterator báo `IMMUTABLE`, **không phải `CONCURRENT`**.

Một danh sách bất biến như `List.of(...)` cũng không cho thêm/xóa phần tử, nhưng vẫn phải kiểm cờ thực sự từ Spliterator nếu thư viện của bạn cần dựa vào nó. Cờ không suy ra chỉ từ tên kiểu; hãy đọc tài liệu và gọi `hasCharacteristics(...)`.

## 5. CONCURRENT: nguồn thay đổi đồng thời một cách an toàn

`Spliterator.CONCURRENT` báo rằng **nguồn phần tử** cho phép nhiều thread thêm, thay thế hoặc xóa mà không cần đồng bộ ngoài, **theo chính sách nhất quán được nhà cung cấp tài liệu hóa**. Đây là khái niệm khác hoàn toàn với việc **dùng một Stream ở chế độ parallel**.

Ví dụ: Spliterator của `ConcurrentHashMap.keySet()` báo `CONCURRENT`. Nó có thể duyệt trong khi map được cập nhật, không mặc định ném `ConcurrentModificationException`. Tuy nhiên, nó **không phải snapshot bất biến**: kết quả duyệt có thể phản ánh những trạng thái khác nhau trong khoảng thời gian duyệt, và không được giả định sẽ thấy chính xác mọi thay đổi đồng thời.

### 5.1. CONCURRENT không đồng nghĩa với tự do chia sẻ một Spliterator

Tài liệu Java nêu rõ: **chính đối tượng Spliterator không được kỳ vọng là thread-safe**. Nhiều thread không nên gọi `tryAdvance()`, `forEachRemaining()` hoặc `trySplit()` đồng thời trên **cùng một đối tượng Spliterator**. Mô hình an toàn của framework là một thread thao tác trên một Spliterator tại mỗi thời điểm; sau khi `trySplit()`, các phần khác nhau có thể được giao cho các thread khác.

`CONCURRENT` nói về **khả năng xử lý sửa đổi nguồn**, không phải giấy phép bỏ quy tắc thread-confinement của Spliterator hoặc thay đổi data source tùy ý.

### 5.2. Những cặp cờ không phù hợp ở Spliterator gốc

Theo hợp đồng Java hiện hành, Spliterator **gốc (top-level)** không nên đồng thời báo:

1. `CONCURRENT` và `SIZED`: nguồn có thể thay đổi số phần tử trong lúc duyệt, nên không thể hứa kích thước hữu hạn sẽ luôn chính xác. Một số **Spliterator con** vẫn có thể báo `SIZED` nếu phần đã tách là ổn định và biết kích thước.
2. `CONCURRENT` và `IMMUTABLE`: nguồn duyệt gốc không thể vừa cho phép thay đổi cấu trúc được phản ánh khi duyệt, vừa bất biến theo cùng nghĩa. Spliterator con dựa trên snapshot có thể báo `IMMUTABLE`.

Báo các tổ hợp không nhất quán khiến API **không bảo đảm kết quả** cho những phép tính dựa vào chúng. Đây không phải cách để “bật mọi tối ưu hóa”.

### 5.3. Chính sách nhất quán phải được kiểm tra riêng

Với collection concurrent, điều quan trọng không phải chỉ có flag `CONCURRENT`, mà còn là tài liệu của nguồn có quy định gì về dữ liệu bị thêm/xóa lúc duyệt. Chẳng hạn `ConcurrentHashMap` cung cấp phép duyệt dạng *weakly consistent*: phần tử quan sát được phản ánh trạng thái ở một thời điểm nào đó từ lúc bộ duyệt được tạo, **không cung cấp snapshot đóng băng toàn bộ map**.

Vì vậy:

- Nếu chỉ làm thống kê gần đúng/giám sát và chấp nhận trạng thái thay đổi, một nguồn concurrent có thể phù hợp.
- Nếu cần kết quả **nhất quán tuyệt đối tại một thời điểm** (đối soát, thanh toán, báo cáo chốt), phải chủ động tạo snapshot hoặc dùng cơ chế đồng bộ/phiên bản thích hợp; `CONCURRENT` không tự cấp tính chất đó.
- Không viết kiểm thử dựa vào việc một phần tử được thêm *đúng trong lúc duyệt* chắc chắn xuất hiện hay chắc chắn không xuất hiện.

## 6. Chương trình chạy được: đọc bốn cờ trên nguồn thực tế

Tạo file `SpliteratorCharacteristicsDemo.java`. Chương trình dùng Java 17+ để tiện khai báo `List.of`, còn các cờ Spliterator đã có từ Java 8. Ví dụ kiểm tra bốn nguồn khác nhau, thử tách một Spliterator `SUBSIZED` và quan sát snapshot.

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Spliterator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.stream.Stream;

public class SpliteratorCharacteristicsDemo {
    static void report(String name, Spliterator<?> spliterator) {
        System.out.printf(
                "%s: SIZED=%b SUBSIZED=%b IMMUTABLE=%b CONCURRENT=%b exact=%d%n",
                name,
                spliterator.hasCharacteristics(Spliterator.SIZED),
                spliterator.hasCharacteristics(Spliterator.SUBSIZED),
                spliterator.hasCharacteristics(Spliterator.IMMUTABLE),
                spliterator.hasCharacteristics(Spliterator.CONCURRENT),
                spliterator.getExactSizeIfKnown());
    }

    public static void main(String[] args) {
        List<Integer> list = new ArrayList<>(List.of(10, 20, 30, 40));
        Spliterator<Integer> original = list.spliterator();
        report("ArrayList", original);

        long sizeBefore = original.estimateSize();
        Spliterator<Integer> prefix = original.trySplit();
        if (prefix == null) {
            throw new AssertionError("Expected the list to split");
        }
        if (!prefix.hasCharacteristics(
                Spliterator.SIZED | Spliterator.SUBSIZED)) {
            throw new AssertionError("Split child must know its size");
        }

        long sizeAfter = prefix.getExactSizeIfKnown()
                + original.getExactSizeIfKnown();
        System.out.println("Split sizes add up: " + (sizeBefore == sizeAfter));

        Spliterator<Integer> set = new HashSet<>(
                List.of(1, 2, 3)).spliterator();
        report("HashSet", set);

        CopyOnWriteArrayList<String> copyOnWrite =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        Spliterator<String> snapshot = copyOnWrite.spliterator();
        report("CopyOnWrite", snapshot);
        copyOnWrite.add("C");
        List<String> seen = new ArrayList<>();
        snapshot.forEachRemaining(seen::add);
        System.out.println("Snapshot sees: " + seen);
        System.out.println("List now: " + copyOnWrite);

        ConcurrentHashMap<Integer, String> map = new ConcurrentHashMap<>();
        map.put(1, "A");
        map.put(2, "B");
        report("CHM keys", map.keySet().spliterator());

        Spliterator<Integer> filtered = Stream.of(1, 2, 3, 4)
                .filter(x -> x % 2 == 0)
                .spliterator();
        System.out.println("Filtered SIZED: "
                + filtered.hasCharacteristics(Spliterator.SIZED));
        System.out.println("Filtered exact size: "
                + filtered.getExactSizeIfKnown());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 SpliteratorCharacteristicsDemo.java
java SpliteratorCharacteristicsDemo
~~~

Một kết quả chạy trên JDK hiện hành:

~~~text
ArrayList: SIZED=true SUBSIZED=true IMMUTABLE=false CONCURRENT=false exact=4
Split sizes add up: true
HashSet: SIZED=true SUBSIZED=false IMMUTABLE=false CONCURRENT=false exact=3
CopyOnWrite: SIZED=true SUBSIZED=true IMMUTABLE=true CONCURRENT=false exact=2
Snapshot sees: [A, B]
List now: [A, B, C]
CHM keys: SIZED=false SUBSIZED=false IMMUTABLE=false CONCURRENT=true exact=-1
Filtered SIZED: false
Filtered exact size: -1
~~~

**Đọc kết quả theo hợp đồng API:**

1. `ArrayList` thông thường biết size và có thể chia thành các nhánh có kích thước được báo chính xác; nó không báo `IMMUTABLE` hay `CONCURRENT`.
2. `Split sizes add up: true` xác minh kích thước đã biết trước khi tách bằng tổng kích thước hai phần sau tách, không phụ thuộc việc số phần tử được chia là 2/2 hay 1/3.
3. `HashSet` được kiểm tra như một ví dụ gốc `SIZED` nhưng không `SUBSIZED` trong JDK đang thử. Đây là đặc điểm của implementation tương ứng; không dùng nó làm giả định cho mọi Set tùy biến.
4. `CopyOnWriteArrayList` báo `IMMUTABLE` trên Spliterator chụp snapshot. Sau khi thêm `"C"` vào collection, Spliterator đã tạo chỉ duyệt `"A"` và `"B"`.
5. `ConcurrentHashMap.keySet()` báo `CONCURRENT` nhưng không báo `SIZED`. `getExactSizeIfKnown()` trả `-1`; điều này **không nói rằng map rỗng** (trong ví dụ map có hai khóa).
6. Pipeline `filter(...)` không thể biết số lượng phần tử còn lại chỉ từ số lượng ban đầu; Spliterator được tạo từ pipeline của ví dụ không báo `SIZED` và `getExactSizeIfKnown()` trả `-1`.

Những giá trị cờ thể hiện ở stdout là kết quả đã xác minh cho các implementation Java được dùng trong ví dụ; khi viết mã thư viện tổng quát, hãy phụ thuộc vào **hợp đồng Spliterator** và kiểm tra cờ thực tế, thay vì cố định cờ cho mọi bộ sưu tập do bên thứ ba triển khai.

## 7. Sự khác nhau khi duyệt tuần tự và song song

`trySplit()` là cơ chế nền tảng để chia công việc. Một luồng song song không phải là yêu cầu rằng mọi Spliterator sẽ chia được hoặc chia đều; `trySplit()` có thể trả `null` nếu không thể hoặc không có lợi khi tách.

**SIZED/SUBSIZED hỗ trợ việc phân chia:** số phần tử đã biết giúp lập kế hoạch và tối ưu bộ đệm, nhưng kết quả parallel còn phụ thuộc chi phí tính toán, cách triển khai, số lõi, dữ liệu, và việc có duy trì encounter order hay không.

**IMMUTABLE giảm lo ngại về structural interference:** nguồn duyệt ổn định tránh tình huống collection bị thay đổi cấu trúc khi pipeline xử lý. Tuy nhiên, callback vẫn phải phù hợp quy tắc Stream: thường cần **non-interfering** và **stateless**. Một object mutable bên trong vẫn có thể bị cập nhật bởi ứng dụng khác; cờ không kiểm soát nội dung object đó.

**CONCURRENT cho phép nguồn được thay đổi an toàn:** nhưng kết quả aggregate của một lần duyệt trên nguồn đang thay đổi có thể không phản ánh một ảnh chụp nhất quán. Chạy `parallel()` không sửa được vấn đề snapshot. Với bài toán cần dữ liệu chốt, phải định nghĩa điểm nhất quán trước.

**Không nên sửa ArrayList trong lúc Stream đang duyệt:** Spliterator có thể fail-fast bằng `ConcurrentModificationException` trên cơ sở *best effort*, nhưng không có bảo đảm sẽ luôn phát hiện ngay hoặc kết quả luôn xác định nếu bạn can thiệp nguồn sai hợp đồng. Đừng dùng exception này làm phương pháp kiểm tra đúng đắn.

## 8. Quy tắc khi tự triển khai Spliterator

Khi tạo nguồn Stream tùy biến từ Spliterator riêng (ví dụ qua `StreamSupport.stream(spliterator, parallel)`), cần khai báo `characteristics()` trung thực. Không cần báo tất cả cờ; báo thiếu một cờ có thể làm lỡ một tối ưu hóa, còn **báo thừa cờ không đúng** có thể vi phạm hợp đồng API.

### 8.1. Bảng quyết định

| Cờ | Chỉ khai báo khi | Không được suy luận |
|---|---|---|
| `SIZED` | Có kích thước hữu hạn chính xác theo hợp đồng trước khi duyệt/chia, nguồn ổn định phù hợp | “Tôi ước lượng gần đúng được, vậy là SIZED” |
| `SUBSIZED` | Mọi lần chia con trực tiếp/gián tiếp tiếp tục biết kích thước chính xác và báo hai cờ | “Root có SIZED nên các child cũng SIZED” |
| `IMMUTABLE` | Nguồn phần tử dùng để duyệt không bị thay đổi cấu trúc trong khoảng duyệt | “Phần tử là final nên toàn bộ nguồn bất biến” |
| `CONCURRENT` | Nguồn hỗ trợ sửa cấu trúc đồng thời an toàn và có chính sách duyệt tài liệu hóa | “Tôi sẽ gọi parallel(), vậy nguồn là CONCURRENT” |

### 8.2. Những bất biến cần test

Với Spliterator tự viết, nên xây dựng các phép thử ít nhất sau:

- Kiểm tra `hasCharacteristics(...)` trả đúng những bit đã được hỗ trợ và **không báo cờ sai**.
- Với `SIZED`, trên nguồn không thay đổi, đếm số phần tử khi duyệt hết và so với `estimateSize()` ở điểm trước traversal. Không biến một ước lượng thành cam kết.
- Với `SUBSIZED`, gọi `trySplit()` lặp lại theo từng nhánh; kiểm mọi nhánh con đều có `SIZED` và `SUBSIZED`. Trước khi duyệt, kiểm kích thước các nhánh sau chia cộng lại bằng kích thước ban đầu.
- Với `IMMUTABLE`, cố gắng thay đổi collection *bên ngoài* (nếu bản thân collection cho phép), rồi xác minh nguồn Spliterator đã chụp hoặc cấu trúc thật sự vẫn phù hợp hợp đồng; không chỉ kiểm tên flag.
- Với `CONCURRENT`, kiểm hành vi khi nguồn thay đổi theo **chính sách công bố**; không khẳng định bắt buộc nhìn thấy mọi phần tử mới.
- Test rỗng, chỉ một phần tử, nguồn rất lớn, nguồn không chia được, duyệt sau một lần split, và các trường hợp bị gián đoạn do exception.
- Nếu chỉ hỗ trợ một thread mỗi Spliterator, không tạo test cho nhiều thread gọi đồng thời trên cùng đối tượng rồi coi đó là hành vi được bảo đảm.

### 8.3. Các lỗi mã nguồn thường gặp

Sai: đánh dấu mọi cờ vì muốn “tối ưu”:

~~~java
int flags = Spliterator.SIZED
        | Spliterator.SUBSIZED
        | Spliterator.IMMUTABLE
        | Spliterator.CONCURRENT;
~~~

Đây là **phản ví dụ**, không phải bộ cờ nên dùng. Spliterator gốc như vậy có cặp `CONCURRENT`/`SIZED` và `CONCURRENT`/`IMMUTABLE` không nhất quán. Nếu nguồn không biết chính xác kích thước hoặc không có chính sách sửa đổi đồng thời, các cờ càng sai.

Đúng: chỉ chọn bộ cờ tương ứng với nguồn cụ thể, có kiểm tra trong implementation và test; không có một bitmask “chuẩn” cho mọi Spliterator. `ORDERED`, `DISTINCT`, `NONNULL` và `SORTED` cũng có hợp đồng riêng nếu implementation chọn công bố chúng.

## 9. Phân biệt nhanh qua tình huống

**Tình huống A — List biết 1000 phần tử.** Có thể khai báo `SIZED` nếu đếm chính xác và nguồn duyệt không bị can thiệp. Chỉ khai `SUBSIZED` khi mọi Spliterator sau chia cũng biết chính xác size và tiếp tục đáp ứng hợp đồng.

**Tình huống B — Danh sách copy-on-write.** Collection có thể được sửa, nhưng Spliterator đã tạo giữ snapshot: `IMMUTABLE` có nghĩa phù hợp với **nguồn duyệt**, không khẳng định collection bị khóa vĩnh viễn.

**Tình huống C — Map concurrent được update.** `CONCURRENT` cho biết nguồn xử lý sửa cấu trúc an toàn; không có quyền diễn giải số phần tử quan sát được như một snapshot cố định tại một thời điểm.

**Tình huống D — Stream đã filter.** Số phần tử sau filter có thể khác nguồn và không được biết trước; không mặc định giữ `SIZED` hay cho `getExactSizeIfKnown()` trả kích thước nguồn.

**Tình huống E — Tăng tốc bằng parallel.** Có `SUBSIZED` thường giúp chia khối lượng tốt hơn, nhưng không bảo đảm chương trình chạy nhanh hơn do chi phí scheduling và đặc tính bài toán.

## 10. Bài tập tự luyện và đáp án

1. Một Spliterator biết root có 10.000 phần tử, nhưng sau `trySplit()` mỗi nhánh chỉ biết ước lượng. Nó có thể báo `SIZED` không? Có nên báo `SUBSIZED` không?
2. Một `CopyOnWriteArrayList` cho phép `add` trong khi Spliterator đã tạo báo `IMMUTABLE`. Tại sao không mâu thuẫn?
3. Nếu `getExactSizeIfKnown()` trả `-1`, bạn có thể kết luận không có phần tử không? Cần làm gì nếu muốn đếm thật?
4. `CONCURRENT` có nghĩa cùng đối tượng Spliterator có thể bị gọi từ 10 thread đồng thời không? Phân biệt “nguồn concurrent” với “spliterator thread-safe”.
5. Vì sao không nên báo đồng thời `CONCURRENT` với `SIZED` hay `IMMUTABLE` trên Spliterator gốc?
6. Nếu nguồn là `ArrayList` `SIZED` nhưng bị thay đổi cấu trúc giữa lúc duyệt, liệu mọi lần chạy chắc chắn ném `ConcurrentModificationException` không?

**Đáp án gợi ý:**

1. `SIZED` có thể phù hợp với root nếu số lượng gốc chính xác theo hợp đồng; **không** khai `SUBSIZED` vì các nhánh không biết size chính xác.
2. Snapshot của Spliterator không đổi; collection mẹ có thể tạo mảng mới khi chỉnh sửa mà không thay đổi snapshot đã được dùng để duyệt.
3. Không. `-1` báo rằng API không biết chính xác kích thước qua cờ `SIZED`; phải duyệt/đếm theo hợp đồng nguồn hoặc dùng dữ liệu thống kê chuyên biệt.
4. Không. `CONCURRENT` nói về nguồn; bản thân Spliterator thường yêu cầu mỗi đối tượng chỉ do một thread sử dụng tại một thời điểm.
5. Vì nó hứa những đặc điểm mâu thuẫn: nguồn thay đổi kích thước khi duyệt nhưng đồng thời size luôn chính xác, hoặc nguồn vừa sửa được vừa bất biến theo cùng mô hình duyệt.
6. Không. Fail-fast chỉ phát hiện can thiệp ở mức *best effort*; sửa nguồn trong lúc duyệt có thể gây kết quả không xác định.

## Ghi nhớ

- **SIZED**: kích thước của Spliterator ban đầu là **chính xác** dưới các điều kiện API, không phải con số gần đúng.
- **SUBSIZED**: các nhánh `trySplit()` đều tiếp tục **SIZED và SUBSIZED**; `SUBSIZED` kéo theo `SIZED`, chiều ngược lại không đúng.
- **IMMUTABLE**: **nguồn duyệt** không bị can thiệp cấu trúc; không cam kết deep immutability cho mọi phần tử hay thread-safety của Spliterator.
- **CONCURRENT**: **nguồn** hỗ trợ thay đổi cấu trúc đồng thời và có chính sách quan sát; không cam kết snapshot hoặc kích thước cố định.
- Không đánh dấu cờ tùy tiện, không dựa vào hiệu năng giả định, và luôn kiểm tra các hợp đồng quan trọng khi tự xây dựng Spliterator.

### Tài liệu chính thức đang áp dụng

- [Oracle Java SE 27 — Spliterator: characteristics, trySplit, estimateSize](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Spliterator.html)
- [Oracle Java SE 27 — Spliterators utilities](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Spliterators.html)
- [Oracle Java SE 27 — CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)
- [Oracle Java SE 27 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html)
- [Oracle Java SE 27 — Stream và tối ưu count](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html)
