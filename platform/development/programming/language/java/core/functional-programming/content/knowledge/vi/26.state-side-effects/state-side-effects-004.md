# Rủi ro thêm kết quả vào `ArrayList` từ `forEach()` song song trong Java Stream

Khi chuyển một pipeline Stream sang chế độ song song bằng `parallel()` hoặc `parallelStream()`, một đoạn mã tưởng như tự nhiên có thể trở nên **không an toàn**:

~~~java
List<Integer> results = new ArrayList<>();

IntStream.range(0, 10_000)
        .parallel()
        .forEach(results::add); // KHÔNG AN TOÀN
~~~

Đây là **ví dụ chống chỉ định**, không nên chạy trong chương trình thật. `ArrayList` là một cấu trúc có trạng thái mutable nhưng **không an toàn cho nhiều thread cùng thay đổi cấu trúc**. Khi `forEach` được thực thi song song, các lần gọi `results.add(...)` có thể đan xen nhau, gây mất phần tử, hỏng dữ liệu hoặc lỗi runtime. Việc chương trình **thỉnh thoảng** in ra đúng 10.000 phần tử không chứng minh nó an toàn.

Giải pháp phù hợp nhất khi mục tiêu là **tạo collection kết quả**: **để Stream tự thu thập bằng `collect()` hoặc `toList()`**, thay vì dùng `forEach()` để thay đổi một collection dùng chung.

~~~java
List<Integer> results = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();

System.out.println(results.size()); // 10000
~~~

Đoạn này dùng `IntStream` tạo số nguyên, `boxed()` đổi thành `Stream<Integer>`, còn `toList()` là terminal tạo danh sách. Nguồn `IntStream.range` có encounter order từ 0 đến 9.999; `Stream.toList()` bảo toàn encounter order đó dù pipeline chạy song song.

## 1. Vấn đề cốt lõi: trạng thái chia sẻ và tác dụng phụ

Trong Stream API, lập trình theo phong cách hàm thường ưu tiên các phép biến đổi **không phụ thuộc trạng thái có thể thay đổi bên ngoài**:

~~~java
List<String> labels = numbers.parallelStream()
        .filter(n -> n > 0)
        .map(n -> "N=" + n)
        .toList();
~~~

Biến `numbers` được giả định là một nguồn danh sách ổn định trong quá trình xử lý. `filter` quyết định dựa trên phần tử, `map` tạo giá trị đầu ra, `toList` thu kết quả. Mã không sửa collection bên ngoài trong từng lần gọi lambda.

Ngược lại:

~~~java
List<String> external = new ArrayList<>();

numbers.parallelStream()
        .filter(n -> n > 0)
        .forEach(n -> external.add("N=" + n)); // Sai nếu chạy song song
~~~

`external.add(...)` là **side effect**: nó thay đổi trạng thái nằm ngoài phần tử đang xử lý và ngoài cơ chế thu thập của framework. Tất cả task cùng tham chiếu một `external`; không có hợp đồng nào của `forEach` khiến một `ArrayList` thường được tự động bảo vệ.

Có hai khái niệm cần tách biệt:

- **Stateless lambda:** kết quả chủ yếu phụ thuộc phần tử đầu vào; không yêu cầu ghi vào biến mutable dùng chung.
- **Thread-safe accumulation:** có thể thay đổi trạng thái tích lũy, nhưng framework hoặc cấu trúc dữ liệu được thiết kế để phối hợp các cập nhật an toàn.

`collect()` cũng có accumulator mutable ở bên trong, nhưng việc tích lũy được quản lý theo hợp đồng Collector. Điều này khác về bản chất so với tự đưa một `ArrayList` bên ngoài vào `forEach()`.

## 2. Vì sao `ArrayList.add()` không an toàn khi nhiều thread cùng ghi?

`ArrayList` thường chứa những trạng thái nội bộ liên quan đến kích thước (`size`) và mảng phần tử. Khi thêm một phần tử, thao tác logic gồm kiểm tra/cấp chỗ, ghi phần tử và cập nhật kích thước. Không có bảo đảm các bước này tạo thành một thao tác nguyên tử đối với nhiều thread.

Hình dung hai thread cùng đọc `size = 5`:

~~~text
Trạng thái ban đầu: size = 5

Thread A                           Thread B
--------                           --------
Đọc size = 5                       Đọc size = 5
Chọn vị trí thêm 5                 Chọn vị trí thêm 5
Ghi phần tử A tại vị trí 5         Ghi phần tử B tại vị trí 5
Tăng/cập nhật size                 Tăng/cập nhật size

Hậu quả có thể: một ghi đè lên ghi kia, bộ đếm không
phản ánh số lượt thêm, hoặc cấu trúc bên trong bị sai.
~~~

Đây là **mô hình minh họa race**, không phải mô tả bắt buộc chính xác từng câu lệnh máy trong một phiên bản JDK. Một số lỗi thường thấy khi cạnh tranh truy cập:

1. **Lost update:** hai thao tác thêm không được phản ánh đầy đủ, nên `list.size()` nhỏ hơn số phần tử dự kiến.
2. **Nội dung sai hoặc thiếu:** kết quả có thể chứa vị trí không mong đợi hoặc mất giá trị, kể cả khi kích thước nhìn có vẻ hợp lệ.
3. **Ngoại lệ:** trong một số trường hợp có thể xuất hiện lỗi chỉ số, ngoại lệ khi thay đổi kích thước hay các lỗi khác do trạng thái nội bộ không nhất quán.
4. **Không dự đoán được thứ tự:** ngay cả một collection thread-safe cho phép nhiều lần `add` song song cũng không tự bảo đảm thứ tự theo nguồn.
5. **Khó tái hiện:** dữ liệu nhỏ hoặc một máy ít lõi có thể tình cờ cho kết quả đúng, rồi sai ở môi trường khác.

Vì vậy không viết unit test "chạy một lần và thấy size đúng" để kết luận an toàn luồng. Lỗi là ở **hợp đồng đồng thời**, không phải xác suất của một lần kiểm thử.

### Chỉ dùng `parallel()` đã có thể thay đổi điều kiện an toàn

Đoạn mã:

~~~java
List<Integer> sink = new ArrayList<>();
IntStream.range(0, 100).forEach(sink::add);
~~~

Trong pipeline tuần tự thông thường, hành động thêm được gọi tuần tự. Nhưng sau khi đổi thành:

~~~java
List<Integer> sink = new ArrayList<>();
IntStream.range(0, 100).parallel().forEach(sink::add);
~~~

hành động có thể được gọi từ nhiều thread. Cùng một đoạn `sink::add` trở thành side effect không an toàn. Hai ví dụ trên là các đoạn **minh họa độc lập**, không đặt đồng thời trong một scope với cùng tên biến.

Không nên xem việc tách ra nhiều `stream()` hoặc thêm `peek()` như một cách giải quyết. Điểm lỗi vẫn là collection mutable được chia sẻ cho những hành động đồng thời.

## 3. `forEach()` không phải công cụ thu thập kết quả

`forEach(Consumer<? super T>)` là **terminal operation** dùng để thực thi một hành động trên từng phần tử. Tài liệu Stream coi đây là thao tác *explicitly nondeterministic* trong pipeline song song: action có thể được gọi ở bất kỳ thread nào mà thư viện chọn; thứ tự thực thi không được đảm bảo chỉ vì nguồn có encounter order.

~~~java
IntStream.range(0, 10)
        .parallel()
        .forEach(System.out::print);
~~~

Đoạn trên hợp lệ về cú pháp nhưng thứ tự chữ số được in **không có kết quả cố định**. Ngay cả khi `System.out.print` có đồng bộ nội bộ thích hợp cho lời gọi riêng, điều đó cũng **không tạo lại encounter order**.

Phân biệt mục tiêu:

| Nhu cầu | Công cụ nên dùng |
| --- | --- |
| Tạo `List<T>` từ kết quả biến đổi | `map(...).toList()` |
| Cần `ArrayList<T>` có thể thêm/xóa | `collect(Collectors.toCollection(ArrayList::new))` |
| Tạo `Set<T>` các giá trị khác nhau | `collect(Collectors.toSet())` hoặc collector Set phù hợp |
| Tính tổng | `mapToInt(...).sum()` hoặc `reduce(...)` |
| Ghi kết quả vào hệ thống ngoài một cách có kiểm soát | Xác định thứ tự, giao thức I/O, backpressure và xử lý lỗi, không mặc định dùng shared mutable list |
| Chỉ quan sát/phụ trợ debug | Cân nhắc log có cấu trúc; không dùng `peek` hoặc `forEach` để tạo kết quả kinh doanh |

Nếu mục tiêu cuối là collection, `forEach` kèm `add` thường là **sai cấp trừu tượng**. Hãy diễn đạt yêu cầu trực tiếp bằng terminal trả collection.

## 4. Cách ưu tiên: `toList()` giữ kết quả mà không chia sẻ list

Từ Java 16, `Stream.toList()` tạo một `List<T>` không hỗ trợ sửa cấu trúc:

~~~java
List<Integer> values = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();
~~~

Với nguồn ordered như `IntStream.range`, kết quả giữ **encounter order**. Framework quản lý quá trình thu thập; người dùng không chuyển một `ArrayList` bên ngoài vào nhiều thread.

**Lưu ý quan trọng về mutability:** `Stream.toList()` là List **unmodifiable**. Lời gọi `values.add(10_000)` ném `UnsupportedOperationException`. Nếu cần thay đổi kết quả, hãy chọn một collector trả cấu trúc phù hợp hoặc tạo bản sao:

~~~java
List<Integer> mutableCopy = new ArrayList<>(values);
mutableCopy.add(10_000);
~~~

Dùng bản sao là hợp lý khi cần bước hậu xử lý có sửa dữ liệu. Không sử dụng `Stream.toList()` rồi giả định giống với `Collectors.toCollection(ArrayList::new)`.

### `Collectors.toList()` khác với `Stream.toList()`

~~~java
List<Integer> a = source.stream().collect(Collectors.toList());
List<Integer> b = source.stream().toList();
~~~

Đây là đoạn minh họa với `source` là một `List<Integer>` sẵn có. Cả hai là kết quả thu thập, nhưng **`Collectors.toList()` không cam kết kiểu triển khai hoặc khả năng sửa của List trả về**, còn `Stream.toList()` cam kết không sửa được. Muốn `ArrayList` chắc chắn có thể sửa, dùng `toCollection(ArrayList::new)`.

Không tái sử dụng cùng một đối tượng `Stream` cho hai terminal; ở ví dụ trên hai lời gọi `source.stream()` là hai Stream mới.

## 5. Cần `ArrayList` mutable: `Collectors.toCollection(ArrayList::new)`

Nếu yêu cầu trả về **đúng một `ArrayList`** có thể thêm/xóa kết quả:

~~~java
ArrayList<Integer> results = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .collect(Collectors.toCollection(ArrayList::new));

results.add(-1);
~~~

Đoạn cần import `java.util.ArrayList`, `java.util.stream.IntStream` và `java.util.stream.Collectors`. Cách này có hai điểm khác so với `parallel().forEach(external::add)`:

1. Supplier `ArrayList::new` tạo **container tích lũy do Collector quản lý**. Khi cần, framework tạo container riêng cho từng phần việc, tích lũy độc lập, rồi kết hợp kết quả.
2. Framework thực hiện theo **hợp đồng collector không concurrent**; không yêu cầu nhiều thread đồng thời gọi `add` trên cùng một `ArrayList` thường.

Vì vậy collector có thể an toàn với parallel stream dù `ArrayList` của từng container **không phải collection thread-safe**. Tính đúng đến từ cách framework phân phối và hợp nhất, chứ không phải từ việc `ArrayList` bí mật hỗ trợ đa luồng.

### Thứ tự kết quả

Với nguồn ordered, collector dạng danh sách và quy tắc kết hợp phù hợp, kết quả giữ encounter order. `parallel()` không đồng nghĩa "list kết quả nhất định bị đảo". Tuy nhiên, nếu chính nguồn đã được đánh dấu unordered, không nên suy luận thứ tự đầu ra tương ứng với một thứ tự đầu vào cố định.

### Không tự tạo collector concurrent sai

Cách làm sai về hợp đồng:

~~~java
// Không làm như sau trong Collector.of:
// Collector.of(
//     ArrayList::new,
//     List::add,
//     (left, right) -> { left.addAll(right); return left; },
//     Collector.Characteristics.CONCURRENT,
//     Collector.Characteristics.UNORDERED
// );
~~~

Nếu công bố `CONCURRENT`, framework có thể cho nhiều thread cập nhật **cùng một container**; `ArrayList::add` không an toàn khi đó. Không tự thêm characteristic chỉ vì mục tiêu là "tăng tốc".

## 6. Nếu bắt buộc có collection dùng chung: chọn cấu trúc thread-safe

Đôi khi việc cập nhật một sink dùng chung thực sự là yêu cầu (ví dụ thu kết quả từ một API callback). Khi ấy phải dùng cấu trúc và giao thức đồng thời thích hợp. Tuy nhiên, đối với bài toán chỉ **collect dữ liệu**, giải pháp ở mục 4–5 vẫn được ưu tiên.

### `Collections.synchronizedList(new ArrayList<>())`

~~~java
List<Integer> shared = Collections.synchronizedList(new ArrayList<>());

IntStream.range(0, 10_000)
        .parallel()
        .forEach(shared::add);
~~~

Ở đây mỗi lời gọi `add` của wrapper được đồng bộ; việc thêm phần tử vào list được bảo vệ trước các lời gọi cùng wrapper. Tuy vậy:

- **Thứ tự chèn** phụ thuộc lịch thực thi, không phải encounter order.
- Các thao tác đơn lẻ được đồng bộ, nhưng một chuỗi thao tác gồm "kiểm tra rồi sửa" vẫn cần một cơ chế đồng bộ chung nếu muốn nguyên tử.
- Duyệt danh sách bằng iterator khi có thread khác sửa cần **đồng bộ bên ngoài theo hướng dẫn của synchronized collection**.
- Mỗi lần `add` cạnh tranh một khóa chung có thể làm nghẽn và mất lợi ích chạy song song.

Ví dụ sau khi tất cả tác vụ hoàn tất:

~~~java
List<Integer> display = shared.stream().sorted().limit(5).toList();
// [0, 1, 2, 3, 4]
~~~

Chỉ gọi `shared.stream()` sau khi terminal `forEach` đã kết thúc và không còn thread khác thay đổi list. `sorted` ở đây chỉ phục vụ hiển thị kết quả xác định, không chứng minh list giữ encounter order khi thêm.

### `ConcurrentLinkedQueue`

Nếu không cần chỉ số của List và chỉ cần ghi nhiều phần tử an toàn:

~~~java
Queue<Integer> queue = new ConcurrentLinkedQueue<>();

IntStream.range(0, 10_000)
        .parallel()
        .forEach(queue::add);
~~~

`ConcurrentLinkedQueue` hỗ trợ thêm phần tử an toàn giữa nhiều thread; nhưng **thứ tự ghi thực tế không nhất thiết theo thứ tự nguồn**. Với ví dụ trên, sau khi terminal hoàn tất, số phần tử là 10.000 nếu mỗi lời gọi đều thành công. Việc biến thành một List được sắp xếp sau đó là một tác vụ riêng.

Không dùng queue để giả vờ có bảo đảm "phần tử đầu nguồn được thêm trước". Một queue thread-safe bảo toàn logic thứ tự queue theo các lời gọi đã xảy ra, không sắp xếp các lời gọi song song theo encounter order của Stream.

### `CopyOnWriteArrayList` không phải phương án mặc định

`CopyOnWriteArrayList` hỗ trợ thread-safe mutation và phù hợp một số workload **rất nhiều đọc, rất ít ghi**. Với hàng nghìn lần `add` liên tục, việc sao chép mảng mỗi lần sửa có thể rất tốn kém. Do đó không nên thay mọi `ArrayList` bằng `CopyOnWriteArrayList` chỉ để hợp thức hóa `parallel().forEach(...)`.

### Bảng chọn sink

| Cách làm | An toàn cập nhật nhiều thread? | Giữ encounter order từ nguồn? | Thường phù hợp |
| --- | --- | --- | --- |
| `new ArrayList<>()` + `parallel().forEach(list::add)` | **Không** | **Không** | Không nên dùng |
| `parallel().toList()` | Framework thu thập an toàn | **Có**, nếu nguồn ordered | Cần List unmodifiable |
| `parallel().collect(toCollection(ArrayList::new))` | Framework thu thập an toàn | **Có**, nếu nguồn ordered và collector giữ order | Cần ArrayList mutable |
| `synchronizedList` + `parallel().forEach(add)` | Có, với từng `add` qua wrapper | **Không** | Sink dùng chung có đồng bộ |
| `ConcurrentLinkedQueue` + `parallel().forEach(add)` | Có | **Không** | Nhiều producer, không đòi List |
| `CopyOnWriteArrayList` + `parallel().forEach(add)` | Có | **Không** | Ít thao tác ghi, nhiều đọc |

Tính an toàn của **bản thân thao tác cập nhật** không đồng nghĩa kết quả có đúng thứ tự nghiệp vụ. Đây là hai tiêu chí độc lập.

## 7. `forEachOrdered()`: sửa thứ tự nhưng không thay thế `collect()`

Trên một stream có encounter order, `forEachOrdered(action)` đảm bảo hành động trên các phần tử được thực hiện theo thứ tự gặp. Javadoc cũng nêu rằng **hành động cho phần tử trước happens-before hành động cho phần tử tiếp theo**. Vì thế, đoạn:

~~~java
List<Integer> ordered = new ArrayList<>();
IntStream.range(0, 10)
        .parallel()
        .forEachOrdered(ordered::add);
~~~

cho kết quả:

~~~text
[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
~~~

Các lời gọi `add` trong chính terminal `forEachOrdered` này được ràng buộc về thứ tự/happens-before, nên không gặp cùng kiểu gọi `add` đồng thời không được sắp thứ tự như `forEach`. Nhưng **đây không phải phương án mặc định để xây một List**:

- Việc giữ thứ tự hiệu ứng phụ có thể làm mất lợi ích song song.
- Hành động có thể chạy trên các thread khác nhau; không giả định cùng một thread.
- Không bảo vệ List trước **những thread khác** có thể sửa nó đồng thời ngoài pipeline.
- Nếu nguồn unordered, không có encounter order có ý nghĩa để `forEachOrdered` tái tạo.
- `collect()` diễn đạt mục đích thu kết quả rõ ràng hơn, tránh dựa vào side effect.

Đừng thay `forEach` bằng `forEachOrdered` chỉ để "chữa" mọi vấn đề thread safety. Nó giải quyết một ràng buộc thứ tự của terminal, **không tự đồng bộ mọi trạng thái bên ngoài hoặc mọi callback bất kỳ**.

## 8. Chương trình Java 17+ đầy đủ, không thực thi data race

Lưu chương trình dưới tên **`ParallelForEachSafeDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelForEachSafeDemo {
    public static void main(String[] args) {
        int size = 10_000;

        List<Integer> result = IntStream.range(0, size)
                .parallel().boxed().toList();

        ArrayList<Integer> mutable = IntStream.range(0, size)
                .parallel().boxed()
                .collect(Collectors.toCollection(ArrayList::new));
        mutable.add(-1);

        List<Integer> evens = IntStream.range(0, size)
                .parallel().filter(n -> n % 2 == 0)
                .boxed().toList();

        Queue<Integer> queue = new ConcurrentLinkedQueue<>();
        IntStream.range(0, size).parallel().forEach(queue::add);

        List<Integer> synchronizedList =
                Collections.synchronizedList(new ArrayList<>());
        IntStream.range(0, size).parallel()
                .forEach(synchronizedList::add);

        List<Integer> ordered = new ArrayList<>();
        IntStream.range(0, 10).parallel()
                .forEachOrdered(ordered::add);

        System.out.println("resultSize=" + result.size());
        System.out.println("firstFive=" + result.subList(0, 5));
        System.out.println("mutableSize=" + mutable.size());
        System.out.println("evenSize=" + evens.size());
        System.out.println("queueSize=" + queue.size());
        System.out.println("queueSmallest=" + queue.stream().sorted().limit(5).toList());
        System.out.println("synchronizedSize=" + synchronizedList.size());
        System.out.println("ordered=" + ordered);
        try {
            result.add(-2);
        } catch (UnsupportedOperationException ex) {
            System.out.println("toListMutation=unsupported");
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17** trở lên:

~~~bash
javac ParallelForEachSafeDemo.java
java ParallelForEachSafeDemo
~~~

Stdout chính xác của chương trình:

~~~text
resultSize=10000
firstFive=[0, 1, 2, 3, 4]
mutableSize=10001
evenSize=5000
queueSize=10000
queueSmallest=[0, 1, 2, 3, 4]
synchronizedSize=10000
ordered=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
toListMutation=unsupported
~~~

Giải thích những điểm cần nghiệm thu:

1. `result` do `toList()` tạo: đủ 10.000 phần tử, giữ thứ tự nguồn ordered `IntStream.range`.
2. `mutable` do `toCollection(ArrayList::new)` tạo một `ArrayList` có thể sửa: sau khi thêm `-1`, kích thước là 10.001.
3. `evens` qua `filter` có 5.000 số chẵn, vẫn thu thập an toàn dù chạy song song.
4. `queue` là cấu trúc concurrent, nên các lượt `add` an toàn. Để in ra năm giá trị nhỏ nhất, code **chủ động sorted sau khi thu thập**; không suy diễn thứ tự tự nhiên từ các lần `forEach`.
5. `synchronizedList` chỉ được dùng một lượt `add` cho mỗi phần tử, rồi đọc kích thước sau khi `forEach` hoàn thành. Không có cập nhật đồng thời với phép đọc kích thước đó.
6. `forEachOrdered` tạo danh sách 0..9 đúng thứ tự của nguồn có encounter order.
7. `result.add(-2)` ném `UnsupportedOperationException` vì `Stream.toList()` trả List unmodifiable. Ngoại lệ được bắt để chương trình vẫn hoàn tất.

Mã **không chứa phép `ArrayList.add` song song không an toàn** trong luồng thực thi. Các ví dụ sai ở phần trước được đưa ra để nhận diện anti-pattern, không dùng làm bài benchmark hay stress test.

## 9. Những cách "sửa nhanh" thường không đúng

### `volatile List` không làm `ArrayList.add` an toàn

~~~java
// Không sửa được race bằng việc khai báo tham chiếu volatile:
// volatile List<Integer> results = new ArrayList<>();
~~~

`volatile` quản lý một số bảo đảm visibility/order cho **tham chiếu field** và việc đọc/ghi field, không tự biến các bước nội bộ của `ArrayList.add` thành phép cập nhật nguyên tử. Hai thread vẫn có thể tranh chấp trên cùng array/size.

### `AtomicInteger` không bảo vệ List

Một bộ đếm nguyên tử có thể đếm số lượt callback, nhưng nó không đồng bộ việc `ArrayList` tự sửa kích thước hoặc mảng. Thậm chí nếu thấy counter đúng 10.000, List vẫn có thể sai.

### `Collections.synchronizedList` không tạo encounter order

Bọc đồng bộ làm từng thao tác thêm an toàn, nhưng thứ tự thread nào lấy được khóa trước có thể khác thứ tự nguồn. Nếu nghiệp vụ cần vị trí phần tử thứ i tương ứng đầu vào thứ i, ưu tiên `toList`/`collect` trên nguồn ordered.

### `parallel()` không tự tăng tốc

Thêm `parallel` tạo overhead chia công việc, gộp kết quả và đồng bộ. Nếu nghiệp vụ chỉ là lấy 10.000 giá trị đơn giản, chạy tuần tự có thể rẻ hơn. Cần đo trên dữ liệu đại diện và phần cứng thật, không dựa vào cảm giác rằng "nhiều thread là nhanh hơn".

### `peek(...)` vẫn không phải chỗ để thu thập kết quả

~~~java
// Không dùng side effect này để tạo kết quả:
// List<Integer> external = new ArrayList<>();
// List<Integer> copy = IntStream.range(0, 10_000)
//         .parallel().boxed()
//         .peek(external::add)
//         .toList();
~~~

`peek` chủ yếu phục vụ quan sát/debug; Stream framework có quyền tối ưu bỏ qua một số bước nếu không ảnh hưởng kết quả theo hợp đồng. Side effect không phải một cách thu thập tin cậy. Nếu `peek` vẫn được gọi đồng thời, race với `external` còn tồn tại.

### `synchronized(list)` thủ công không phải lựa chọn gọn nhất cho collect

~~~java
// Có thể làm việc cho từng lời gọi add, nhưng tăng contention:
// parallelStream.forEach(x -> {
//     synchronized (list) {
//         list.add(x);
//     }
// });
~~~

Đây là **đoạn mã minh họa** với `parallelStream` và `list` đã tồn tại trong phương thức, không phải chương trình tự chạy. Khi công việc chính chỉ là thu thành danh sách, `collect(Collectors.toCollection(ArrayList::new))` rõ nghĩa hơn và không khóa một list dùng chung trên từng phần tử.

## 10. Kiểm thử và phân tích data race

Khi review code có `parallelStream()` hoặc `parallel()`, hãy tìm các biểu thức:

~~~java
.forEach(list::add)
.forEach(x -> result.add(x))
.forEach(map::put)
.peek(x -> external.add(x))
~~~

Chúng không **luôn** sai: cần xét `list/map` có phải trạng thái dùng chung, thread-safe hay không, và cách giải quyết conflict. Nhưng đây là tín hiệu để kiểm tra kỹ:

- `list` được tạo ngoài pipeline rồi truyền vào lambda?
- Nhiều thread có thể thay đổi cùng đối tượng không?
- Có cấu trúc dữ liệu/đồng bộ bảo đảm thao tác nguyên tử?
- Thứ tự kết quả có phải hợp đồng của nghiệp vụ?
- Callback có được phép chạy nhiều lần, chạy ở các thread khác nhau hoặc bị tối ưu bỏ qua?
- Kết quả có thể được xây bằng `collect`/`reduce` thay vì side effect?

Một stress test chạy hàng trăm lần với nhiều phần tử có thể **phát hiện** lỗi race, nhưng nếu test chạy thành công cũng **không chứng minh** code đúng. Race có tính phụ thuộc lịch scheduling. Dùng lập luận theo Java Memory Model, hợp đồng của collection, công cụ phân tích và thử nghiệm đa cấu hình để củng cố kết luận.

Với dữ liệu cố định như `IntStream.range(0, N)`, có thể kiểm tra cả count và tập giá trị:

~~~java
List<Integer> values = IntStream.range(0, 10_000)
        .parallel().boxed().toList();

boolean sizeCorrect = values.size() == 10_000;
boolean endpointsCorrect = values.get(0) == 0 && values.get(9_999) == 9_999;
~~~

Đây là **đoạn minh họa**, yêu cầu import `List` và `IntStream`. Những assertion này kiểm tra đầu ra của giải pháp an toàn. Nếu dùng list unsafe và có test đếm đủ phần tử, vẫn không thay thế việc sửa thiết kế race.

## 11. Liên quan đến `reduce()`, `collect()` và nguyên tắc non-interference

Một Stream pipeline đúng nên hạn chế làm thay đổi nguồn hoặc một trạng thái chung trong quá trình duyệt.

- **Non-interference:** các hàm behavioral không nên sửa nguồn dữ liệu trong lúc stream đang hoạt động (trừ trường hợp nguồn được thiết kế cho cập nhật đồng thời và API/hợp đồng cho phép).
- **Statelessness:** đừng để kết quả lambda phụ thuộc vào một trạng thái mutable có thể biến đổi qua các phần tử hoặc nhiều thread mà thiếu hợp đồng đúng.
- **Associative reduction:** nếu dùng `reduce` song song, phép gộp phải có tính kết hợp thích hợp; không dùng một accumulator mutable dùng chung với phép giảm tưởng như không trạng thái.
- **Collector isolation:** collector không-concurrent có thể dùng trong parallel stream vì framework quản lý các container tích lũy theo hợp đồng, không phải vì các container tự động thread-safe.

Ví dụ tổng số chẵn nên dùng:

~~~java
long evenSum = IntStream.range(0, 10_000)
        .parallel()
        .filter(n -> n % 2 == 0)
        .asLongStream()
        .sum();
~~~

Thay vì đồng bộ một biến counter từ mọi callback. Cách dùng primitive `sum` giúp thể hiện ý định tổng hợp và tránh nhiều side effect.

Lưu ý: `Collectors.toList()` không cam kết trả List mutable; `Stream.toList()` là unmodifiable; `Collectors.toCollection(ArrayList::new)` được chọn khi cần `ArrayList` cụ thể. Cả ba có mục đích khác nhau dù có thể cùng tạo kết quả chứa những phần tử tương tự.

## 12. Checklist sửa mã nguy hiểm trong dự án

| Câu hỏi | Hướng xử lý |
| --- | --- |
| `forEach` đang ghi vào `ArrayList` khai báo bên ngoài? | Ưu tiên thay bằng `map/filter + toList/collect` |
| Kết quả phải là List sửa được? | `Collectors.toCollection(ArrayList::new)` |
| Kết quả cần giữ thứ tự nguồn? | Dùng nguồn ordered và collector/terminal giữ encounter order |
| Kết quả chỉ cần tập giá trị? | `Collectors.toSet()` hoặc Set phù hợp, không dựa vào thứ tự duyệt |
| Thật sự phải có shared sink? | Chọn collection/concurrent queue thích hợp, quản lý thứ tự và contention riêng |
| Chỉ cần tuần tự hóa hành động in/gửi? | Xem `forEachOrdered`, nhưng xác định chi phí và tính chất I/O |
| Muốn nhiều thread thêm vào list mà vẫn giữ index? | Thiết kế xử lý theo index/range rõ ràng thay vì `forEach(add)` dùng chung |
| Code vẫn đúng khi chạy một lần? | Chưa đủ: xem hợp đồng thread safety và scheduling |
| Đổi `parallel` sang `sequential` là xong? | Có thể loại bỏ race trong pipeline đó, nhưng vẫn phải xét cập nhật từ các thread khác và side effect |
| Muốn tối ưu hiệu năng? | Đo với JMH, dữ liệu thực, allocation và contention; không đánh đổi tính đúng lấy tốc độ |

**Tóm lại:** `ArrayList.add()` không an toàn khi nhiều thread đồng thời sửa cùng một List. `parallelStream().forEach(list::add)` đưa trạng thái mutable ra ngoài cơ chế thu thập của Stream, dễ gây data race, mất phần tử và kết quả không ổn định. Khi cần **kết quả dữ liệu**, hãy dùng **`toList()` hoặc `collect(toCollection(ArrayList::new))`**. Chỉ dùng shared mutable sink khi có yêu cầu rõ và đã thiết kế đồng bộ, thứ tự, hiệu năng cùng cách xử lý lỗi tương ứng.