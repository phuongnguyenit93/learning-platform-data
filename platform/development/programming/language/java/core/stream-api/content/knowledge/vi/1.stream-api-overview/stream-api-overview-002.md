# Phân biệt Stream, Collection, Iterator và luồng vào ra

> **Chương:** Tổng quan Stream API  
> **Phạm vi:** Java Stream API (`java.util.stream`), các cấu trúc dữ liệu trong `java.util` và luồng vào/ra trong `java.io`, `java.nio.file`.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **Collection lưu dữ liệu**, **Iterator duyệt dữ liệu**, còn **Stream mô tả phép xử lý trên nguồn dữ liệu**.
2. Phân biệt `java.util.stream.Stream<T>` với `InputStream`, `OutputStream`, `Reader` và `Writer`, dù chúng cùng có chữ *stream*.
3. Nhận diện pipeline Stream gồm **nguồn → thao tác trung gian → thao tác kết thúc**, có thể xử lý lazy và chỉ được sử dụng một lần.
4. Chọn đúng công cụ cho các bài toán truy cập phần tử, biến đổi, tổng hợp, đọc file và quản lý tài nguyên.
5. Tránh các nhầm lẫn thường gặp về bộ nhớ, thứ tự, thay đổi nguồn và xử lý song song.

## 1. Bốn khái niệm trả lời bốn câu hỏi khác nhau

Giả sử ứng dụng có danh sách đơn hàng. Bạn cần giữ các đơn hàng để truy cập về sau, duyệt thủ công từng đơn, lọc đơn hợp lệ để tính tổng hoặc đọc dữ liệu đơn hàng từ tệp. Bốn nhu cầu này liên quan đến nhau nhưng **không cùng một khái niệm**.

| Khái niệm | Câu hỏi chính | Ví dụ Java | Vai trò |
|---|---|---|---|
| **Collection** | *Dữ liệu được giữ ở đâu, tổ chức thế nào?* | `List`, `Set`, `Queue` | Chứa và quản lý các phần tử; có thể truy cập/duyệt nhiều lần. |
| **Iterator** | *Làm sao lấy lần lượt phần tử tiếp theo?* | `Iterator<E>` | Con trỏ duyệt, cho phép chương trình tự điều khiển tiến trình lấy phần tử. |
| **Stream API** | *Cần áp dụng những phép xử lý nào lên dữ liệu?* | `Stream<T>`, `IntStream` | Xây pipeline khai báo như `filter`, `map`, `reduce`, `collect`; tiêu thụ một lần. |
| **Luồng I/O** | *Byte hoặc ký tự đi vào/ra chương trình ra sao?* | `InputStream`, `OutputStream`, `Reader`, `Writer` | Đọc/ghi dữ liệu từ tệp, mạng, bộ nhớ hoặc thiết bị; thường cần đóng tài nguyên. |

Sơ đồ khái niệm:

~~~text
List / Set / nguồn sinh dữ liệu
        │
        ├── iterator() ──> Iterator ──> hasNext(), next() ──> tự điều khiển vòng lặp
        │
        └── stream()   ──> Stream ──> filter() ──> map() ──> terminal operation
                                                      │
                                              kết quả / tác động
                                                      │
                                           List, số, Optional, ...
                                           (tùy thao tác kết thúc)

Tệp / mạng ──> InputStream hoặc Reader ──> đọc byte / ký tự
                      │
                      └── có thể được chuyển thành nguồn cho Stream<T>
                          (ví dụ: Files.lines(...) -> Stream<String>)
~~~

**Điểm cốt lõi:** `Stream<T>` không phải là một loại `Collection<T>`, và `InputStream` không phải là một dạng `Stream<T>`. Hai loại có thể kết hợp với nhau nhưng có API, hợp đồng và mục đích khác nhau.

## 2. Collection: sở hữu cấu trúc lưu trữ, không mô tả pipeline

`Collection<E>` là interface gốc của nhiều cấu trúc chứa phần tử trong `java.util`: `List` giữ vị trí, `Set` loại bỏ phần tử trùng theo quy tắc bằng nhau, `Queue` hỗ trợ xử lý dạng hàng đợi. Tùy cài đặt, collection có thể thay đổi được hoặc không.

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>(List.of("An", "Bình", "Chi"));

System.out.println(names.size()); // 3
System.out.println(names.get(0)); // An: get(index) là phương thức của List
names.add("Dũng");                 // Thay đổi dữ liệu đang giữ

for (String name : names) {
    System.out.println(name);
}
~~~

Ở đây, `names` vẫn tồn tại sau vòng lặp và có thể được duyệt lại. `ArrayList` giữ tham chiếu tới các phần tử trong một cấu trúc có thể thay đổi. Không phải collection nào cũng hỗ trợ `get(index)`: đây là khả năng riêng của `List`. Cũng không phải collection nào cũng cho phép `add` hoặc `remove`: chẳng hạn `List.of(...)` tạo list không thể thay đổi cấu trúc.

Gọi `names.stream()` **không chuyển** `names` thành đối tượng Stream và **không xóa** dữ liệu nguồn. Lệnh đó tạo một Stream để xây phép xử lý lấy dữ liệu từ collection.

~~~java
import java.util.List;

List<Integer> numbers = List.of(2, 3, 4, 5, 6);

List<Integer> squaredEvens = numbers.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .toList();

System.out.println(squaredEvens); // [4, 16, 36]
System.out.println(numbers);       // [2, 3, 4, 5, 6]
~~~

`numbers` là nơi có dữ liệu gốc. `numbers.stream()` tạo pipeline, còn `toList()` tạo **một kết quả đã materialize** (hiện thực hóa thành list) sau khi pipeline chạy. Từ Java 16, `Stream.toList()` trả về list không thể thay đổi cấu trúc; đừng gọi `add` lên kết quả đó. Nếu cần danh sách thay đổi được, có thể dùng `collect(Collectors.toCollection(ArrayList::new))`.

Collection có thể được đọc lại bằng cách tạo Iterator hoặc Stream **mới**. Bản thân Stream đã tiêu thụ thì không thể “tua về đầu” chỉ bằng cách gọi lại thao tác kết thúc.

## 3. Iterator: duyệt ngoài (*external iteration*)

`Iterator<E>` là giao diện có hai thao tác chính:

- `hasNext()`: còn phần tử nào có thể lấy tiếp không?
- `next()`: lấy phần tử kế tiếp và tiến con trỏ duyệt.

Một số iterator còn hỗ trợ `remove()` để xóa **phần tử vừa lấy** khỏi collection nguồn theo đúng hợp đồng của iterator; khả năng này là tùy chọn.

~~~java
import java.util.Iterator;
import java.util.List;

List<Integer> values = List.of(3, 8, 5, 12);
Iterator<Integer> it = values.iterator();

while (it.hasNext()) {
    int value = it.next();

    if (value > 10) {
        System.out.println("Gặp giá trị lớn hơn 10: " + value);
        break; // Người viết quyết định thời điểm dừng
    }
}
~~~

Với Iterator, vòng lặp điều khiển trực tiếp khi nào hỏi phần tử tiếp theo, khi nào dừng, khi nào bỏ qua hoặc xử lý. Vòng lặp `for (T value : iterable)` là cú pháp gọn cho một kiểu duyệt bằng Iterator trên đối tượng `Iterable` (mảng được xử lý bằng cơ chế riêng).

Nếu mục đích là xóa trong lúc duyệt một **collection cho phép thay đổi**, dùng `Iterator.remove()` thường đúng hơn việc tự gọi `collection.remove(...)` ngay trong vòng lặp:

~~~java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));
Iterator<Integer> it = numbers.iterator();

while (it.hasNext()) {
    if (it.next() % 2 == 0) {
        it.remove(); // ArrayList iterator hỗ trợ remove
    }
}
System.out.println(numbers); // [1, 3]
~~~

Không phải mọi Iterator đều hỗ trợ `remove()`. Nếu không hỗ trợ, phương thức này có thể ném `UnsupportedOperationException`. Chỉnh sửa cấu trúc một collection từ bên ngoài khi đang duyệt có thể gây hành vi không xác định theo hợp đồng iterator, thường gặp `ConcurrentModificationException` ở các iterator kiểu *fail-fast*; không nên xem ngoại lệ này là cơ chế bảo đảm an toàn đồng thời.

### Iterator khác Stream ở quyền điều khiển

Với Iterator, mã gọi `next()` để **kéo** từng phần tử. Với Stream, mã khai báo *cần làm gì* bằng các thao tác rồi thư viện tự điều phối quá trình duyệt khi kích hoạt thao tác kết thúc (*internal iteration*). Nhờ đó, Stream có thể áp dụng tối ưu hóa, dừng sớm và phân chia xử lý khi thích hợp.

`Spliterator` cũng là một cơ chế duyệt nguồn, có khả năng mô tả đặc điểm dữ liệu và chia nhỏ phạm vi duyệt để hỗ trợ xử lý song song. Nó là nền tảng quan trọng của Stream, nhưng không đồng nghĩa với Stream và không phải lựa chọn mặc định cho thao tác duyệt thủ công đơn giản.

## 4. Stream API: pipeline xử lý khai báo

Một pipeline Stream có ba phần:

1. **Nguồn**: collection, mảng, tệp, hàm sinh phần tử, v.v.
2. **Thao tác trung gian** (*intermediate operations*): `filter`, `map`, `distinct`, `sorted`, `limit`, v.v. Chúng thường trả về một Stream mới và **lazy**.
3. **Thao tác kết thúc** (*terminal operation*): `count`, `forEach`, `findFirst`, `reduce`, `collect`, `toList`, v.v. Kích hoạt việc tiêu thụ pipeline và cho ra kết quả hoặc tác động.

~~~java
import java.util.List;

List<String> names = List.of("An", "Bình", "Bảo", "Chi");

List<String> result = names.stream()          // Nguồn
        .filter(name -> name.startsWith("B")) // Trung gian: lọc
        .map(String::toUpperCase)             // Trung gian: biến đổi
        .toList();                            // Kết thúc: lấy List

System.out.println(result); // [BÌNH, BẢO]
~~~

Không có list tạm nào **bắt buộc** phải được tạo giữa `filter` và `map`. Stream mô tả chuỗi xử lý, sau đó thư viện điều phối dữ liệu đi qua các bước. Tuy nhiên, thao tác có trạng thái như `sorted` hoặc `distinct` đôi lúc cần lưu thông tin/buffer; **lazy không có nghĩa luôn tốn bộ nhớ O(1)**.

### 4.1. Lazy: định nghĩa pipeline chưa đồng nghĩa với chạy

~~~java
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

List<String> names = List.of("An", "Bình", "Bảo", "Chi");

Stream<String> filtered = names.stream().filter(name -> {
    System.out.println("Đang kiểm tra: " + name);
    return name.startsWith("B");
});

System.out.println("Đã khai báo pipeline");
Optional<String> first = filtered.findFirst();
System.out.println(first.orElse("Không có"));
~~~

Với nguồn `List` có thứ tự và pipeline tuần tự này, kết quả quan sát được là:

~~~text
Đã khai báo pipeline
Đang kiểm tra: An
Đang kiểm tra: Bình
Bình
~~~

`filter` không chạy khi mới khai báo. `findFirst()` bắt đầu duyệt và có thể **dừng sớm** sau phần tử thỏa mãn đầu tiên. Do đó “cứ có `filter` thì quét hết nguồn” là nhận định sai. Với stream song song, thời điểm thực thi và việc xử lý bao nhiêu phần tử có thể khác; tránh phụ thuộc vào tác dụng phụ như `println` trong thao tác trung gian.

### 4.2. Một Stream chỉ tiêu thụ một lần

~~~java
import java.util.List;
import java.util.stream.Stream;

Stream<Integer> stream = List.of(1, 2, 3).stream();

long count = stream.count();         // Lần tiêu thụ duy nhất
System.out.println(count);          // 3

// stream.forEach(System.out::println);
// Không hợp lệ: Stream đã được tiêu thụ; thường gây IllegalStateException.
~~~

Nếu cần hai phép xử lý độc lập, hãy tạo hai Stream từ nguồn có thể duyệt lại:

~~~java
List<Integer> source = List.of(1, 2, 3);

long count = source.stream().count();
int sum = source.stream().mapToInt(Integer::intValue).sum();
~~~

Tạo lại Stream từ nguồn **không bảo đảm** nguồn luôn tái sử dụng được: một kết nối mạng, tệp đã đóng hoặc nguồn sinh chỉ cho phép đọc một lần có thể không hỗ trợ điều đó. `Stream` không tự lưu bản sao dữ liệu đầu vào.

### 4.3. Stream không nhất thiết biến đổi collection gốc

Các thao tác `filter`, `map` tạo kết quả xử lý; chúng không xóa/thay thế phần tử trong `source`. Nếu phần tử là đối tượng mutable, mã trong `map` hoặc `forEach` **vẫn có thể** thay đổi trạng thái đối tượng đó, nhưng đó là tác dụng phụ của mã ứng dụng và thường gây khó kiểm soát.

Không nên sửa trực tiếp nguồn đang được Stream duyệt, trừ khi nguồn và cơ chế duyệt công khai hỗ trợ việc đó. Quy tắc *non-interference* của Stream yêu cầu các hàm xử lý không can thiệp vào nguồn dữ liệu không hỗ trợ truy cập đồng thời. Trong pipeline song song, các hàm có trạng thái hoặc phụ thuộc thứ tự thực thi càng dễ cho ra kết quả bất ngờ.

### 4.4. Các kiểu kết quả khác nhau

Không phải pipeline nào cũng trả về Collection:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> names = List.of("An", "Ánh", "Bình", "Bảo", "Chi");

long total = names.stream().count(); // long

boolean hasNameB = names.stream()
        .anyMatch(name -> name.startsWith("B")); // boolean

Map<Character, List<String>> byInitial = names.stream()
        .collect(Collectors.groupingBy(name -> name.charAt(0)));
        // Map<Character, List<String>>, một kết quả được gom nhóm
~~~

Ở ví dụ trên, `'A'` và `'Á'` là hai ký tự khác nhau, nên nhóm được chia theo **ký tự đầu tiên chính xác** chứ không tự chuẩn hóa dấu tiếng Việt. Các thao tác chuyên sâu khác của module gồm `reduce`, collector tùy chỉnh, `Spliterator`, xử lý song song và Stream Gatherers; tất cả đều dựa trên việc phân biệt **nguồn dữ liệu** với **pipeline xử lý**.

## 5. Luồng vào/ra: truyền byte và ký tự

Chữ *stream* trong **Stream API** và trong **I/O stream** biểu thị những khái niệm khác nhau:

- `java.io.InputStream`: đọc **byte** từ một nguồn.
- `java.io.OutputStream`: ghi **byte** ra một đích.
- `java.io.Reader`: đọc **ký tự**, có liên quan đến giải mã byte theo charset khi dùng loại reader tương ứng.
- `java.io.Writer`: ghi **ký tự**, có thể mã hóa thành byte qua charset.

Các luồng I/O xử lý vận chuyển dữ liệu và quản lý tài nguyên. Chúng không cung cấp trực tiếp pipeline `filter()` / `map()` / `collect()` của `java.util.stream.Stream<T>`.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("data.bin");

try (InputStream in = Files.newInputStream(path)) {
    int first = in.read(); // 0..255 hoặc -1 nếu hết dữ liệu
    System.out.println(first);
} catch (IOException e) {
    System.err.println("Không đọc được tệp: " + e.getMessage());
}
~~~

`read()` ở đây lấy **một byte** (dưới dạng `int`), không lấy một phần tử `T` theo pipeline. Lệnh `try-with-resources` đảm bảo `in.close()` được gọi khi thoát khối, kể cả lúc phát sinh ngoại lệ.

### 5.1. Đọc văn bản qua Reader

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

Path path = Path.of("notes.txt");

try (BufferedReader reader =
             Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line); // Tự điều khiển vòng đọc
    }
} catch (IOException e) {
    System.err.println("Không đọc được tệp: " + e.getMessage());
}
~~~

Đoạn này dùng vòng lặp đọc ký tự theo dòng. Nó phù hợp khi cần điều khiển chi tiết đọc/ghi, xử lý giao thức, hoặc quyết định mỗi bước đọc phụ thuộc vào trạng thái I/O.

### 5.2. Điểm giao: I/O có thể cung cấp nguồn cho Stream API

`Files.lines(path, charset)` trả về **`Stream<String>`**. Nguồn của Stream này là tệp, nên nó vừa dùng pipeline của Stream API, vừa sở hữu tài nguyên cần đóng.

~~~java
import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

Path path = Path.of("orders.txt");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    List<String> firstTen = lines
            .map(String::trim)
            .filter(line -> !line.isEmpty())
            .limit(10)
            .toList();

    firstTen.forEach(System.out::println);
} catch (IOException | UncheckedIOException e) {
    System.err.println("Lỗi đọc tệp: " + e.getMessage());
}
~~~

Ở đây:

1. **`Files.lines(...)`** tạo Stream lấy từng dòng từ tệp khi cần, không bắt buộc đọc toàn bộ tệp vào một list ngay lúc mở.
2. **`map`**, **`filter`** và **`limit`** tạo pipeline xử lý văn bản.
3. **`toList`** kích hoạt pipeline và thu kết quả vào bộ nhớ; nhờ `limit(10)` nên kết quả chứa tối đa 10 dòng không rỗng.
4. **`try-with-resources`** đóng Stream; đối với Stream do `Files.lines` tạo, thao tác đóng cũng giải phóng tài nguyên tệp liên quan.
5. Lỗi khi mở tệp có thể là `IOException`; lỗi đọc phát sinh trong quá trình tiêu thụ Stream có thể được bọc trong `UncheckedIOException`.

**Lưu ý quan trọng:** Đóng một `Stream` tự tạo từ `BufferedReader.lines()` **không tự bảo đảm** đóng `BufferedReader`. Khi gọi `reader.lines()`, hãy quản lý vòng đời của chính `reader` bằng `try-with-resources`, hoặc dùng `Files.lines(...)` như ví dụ trên.

### 5.3. Stream thường không cần đóng; Stream gắn I/O thì cần

`Stream` mở rộng `AutoCloseable` và có thể gọi `close()`, nhưng đa số Stream đến từ `List.stream()`, `Arrays.stream()` hay `Stream.of(...)` không giữ tài nguyên ngoài cần giải phóng. Ngược lại, Stream do `Files.lines` hoặc `Files.walk` tạo có thể giữ tài nguyên hệ thống nên **phải được đóng** đúng cách. Không nên đồng nhất “Stream API là nguồn dữ liệu vô trạng thái” với “mọi Stream đều không cần đóng”.

## 6. Đặt bốn cách tiếp cận cạnh nhau trong cùng một bài toán

Yêu cầu: từ dãy `[5, 12, 7, 20, 9]`, chọn số chẵn rồi tính tổng.

**Collection** là nguồn dữ liệu chung:

~~~java
List<Integer> numbers = List.of(5, 12, 7, 20, 9);
~~~

**Iterator** — chủ động lấy từng phần tử:

~~~java
import java.util.Iterator;
import java.util.List;

List<Integer> numbers = List.of(5, 12, 7, 20, 9);
Iterator<Integer> it = numbers.iterator();

int sum = 0;
while (it.hasNext()) {
    int n = it.next();
    if (n % 2 == 0) {
        sum += n;
    }
}
System.out.println(sum); // 32
~~~

**Stream API** — mô tả phép lọc và tổng hợp:

~~~java
import java.util.List;

List<Integer> numbers = List.of(5, 12, 7, 20, 9);

int sum = numbers.stream()
        .filter(n -> n % 2 == 0)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(sum); // 32
~~~

**I/O** — chỉ cần khi dãy số nằm ngoài chương trình, ví dụ trong tệp. Đọc dữ liệu trước hoặc dùng tệp làm nguồn cho Stream:

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("numbers.txt"); // Mỗi dòng chứa một số nguyên hợp lệ

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    int sum = lines
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .mapToInt(Integer::parseInt)
            .filter(n -> n % 2 == 0)
            .sum();

    System.out.println(sum); // 32 nếu tệp chứa 5, 12, 7, 20, 9
} catch (IOException e) {
    System.err.println("Không mở/đọc được tệp: " + e.getMessage());
}
~~~

Ví dụ cuối giả định các dòng không rỗng là số nguyên hợp lệ; `Integer.parseInt` sẽ ném `NumberFormatException` nếu dữ liệu không đúng định dạng. Nếu lỗi đọc phát sinh trong khi tiêu thụ Stream, cần xử lý thêm `UncheckedIOException` theo chính sách lỗi của ứng dụng.

Cả hai cách duyệt bằng Iterator và Stream đều có thể giải bài toán. Chúng khác nhau chủ yếu ở **mức độ điều khiển** và **khả năng biểu đạt chuỗi phép biến đổi**. I/O giải quyết một vấn đề khác: đưa dữ liệu từ bên ngoài vào trước hoặc trong khi tính toán.

## 7. Bảng so sánh chi tiết

| Tiêu chí | Collection | Iterator | Stream API | I/O stream / Reader / Writer |
|---|---|---|---|---|
| **Bản chất** | Vật chứa dữ liệu | Trạng thái duyệt từng phần tử | Pipeline tính toán trên một nguồn | Kênh đọc/ghi byte hoặc ký tự |
| **API điển hình** | `size`, `add`, `contains` | `hasNext`, `next` | `filter`, `map`, `reduce`, `collect` | `read`, `write`, `flush`, `close` |
| **Cách dùng lặp lại** | Thường tạo được nhiều lượt duyệt | Mỗi iterator tiến dần, thường tạo iterator mới để duyệt lại | Mỗi Stream chỉ được tiêu thụ một lần | Thường đọc/ghi tuần tự; khả năng tua lại tùy nguồn |
| **Cách điều khiển** | Truy cập và quản lý phần tử | External iteration | Internal iteration | Điều khiển việc đọc/ghi dữ liệu |
| **Lazy?** | Cấu trúc chứa dữ liệu đã sẵn sàng; một số view có thể tính khi truy cập | Lấy phần tử theo từng lần `next` | Thao tác trung gian thường lazy | Đọc/ghi xảy ra theo lời gọi và bộ đệm |
| **Kết quả** | Các phần tử đang lưu | Phần tử kế tiếp | Giá trị, `Optional`, mảng, collection hoặc tác động | Dữ liệu đã đọc/ghi |
| **Quản lý tài nguyên** | Tùy cài đặt/nguồn, thông thường không cần close | Thông thường không có close chung | Thường không; bắt buộc quan tâm nếu có nguồn I/O | Thường phải close khi sở hữu tài nguyên |
| **Song song** | Cần cơ chế đồng thời thích hợp | Không mặc định chia nhỏ xử lý | Có `parallel()` nhưng phải tuân thủ hợp đồng xử lý song song | Không tự trở thành pipeline song song |

Không nên suy luận rằng một API luôn nhanh hơn API khác. Stream giúp biểu đạt logic biến đổi, nhưng có thể phát sinh boxing/unboxing, chi phí lambda hoặc lưu đệm ở thao tác có trạng thái. Vòng lặp thủ công đôi khi đơn giản và hiệu quả hơn. Xử lý song song bằng `parallelStream()` hoặc `parallel()` có thêm chi phí chia việc, đồng bộ và gộp kết quả, nên phải đo theo dữ liệu thực tế.

## 8. Những nhầm lẫn cần tránh

**“Stream là Collection kiểu mới.”** Sai: Collection giữ dữ liệu; Stream mô tả cách tiêu thụ dữ liệu. Stream có thể lấy dữ liệu từ collection hoặc từ nguồn không phải collection.

**“`stream()` sao chép toàn bộ List.”** Không có bảo đảm hay yêu cầu như vậy. Pipeline thường lấy dữ liệu từ nguồn khi chạy. Một số thao tác kết thúc như `toList()` mới materialize kết quả.

**“Có thể dùng một Stream cho nhiều phép tính.”** Không. Sau một thao tác kết thúc hoặc khi đã đóng, phải tạo Stream mới nếu nguồn hỗ trợ.

**“Lệnh `filter` chạy ngay lập tức.”** Thông thường không. Nó là thao tác trung gian lazy; thao tác kết thúc mới kích hoạt pipeline. Thư viện cũng có thể tối ưu bỏ qua một số bước khi điều đó không ảnh hưởng kết quả, nên đừng dùng tác dụng phụ trong `map`/`peek` để làm logic bắt buộc.

**“`forEach` luôn giữ đúng thứ tự.”** Không, đặc biệt với pipeline song song. Nếu cần bảo toàn *encounter order* của nguồn có thứ tự, cân nhắc `forEachOrdered` và hiểu rằng điều này có thể giảm lợi ích song song.

**“Stream làm thay đổi nguồn như Iterator.remove.”** Không phải mặc định. Stream thiên về xử lý không can thiệp vào nguồn; `Iterator.remove` là một thao tác sửa nguồn có hợp đồng cụ thể, nếu được hỗ trợ.

**“Mọi thứ mang tên Stream đều có `map` và `filter`.”** `InputStream` đọc byte; `Stream<T>` xử lý phần tử `T`; chúng thuộc các hệ API khác nhau.

**“`Files.lines` tự đóng khi gọi `count` hoặc `toList`.”** Không. Thao tác kết thúc không tự động thay thế việc `close`; hãy dùng `try-with-resources`.

## 9. Chọn công cụ nào trong thực tế?

| Nhu cầu | Lựa chọn thường phù hợp | Vì sao |
|---|---|---|
| Lưu danh sách để tra cứu, thêm, xóa, duyệt lại | `List`, `Set`, `Map` (theo bài toán) | Cần cấu trúc chứa dữ liệu lâu dài; `Map` không kế thừa `Collection` nhưng cũng là cấu trúc dữ liệu. |
| Duyệt tuần tự và quyết định chính xác khi nào lấy phần tử | `Iterator`, `for-each`, vòng lặp | Quyền điều khiển nằm ở người viết. |
| Xóa phần tử ngay trong lúc duyệt collection mutable | `Iterator.remove` nếu được hỗ trợ hoặc API xóa chuyên dụng | Tuân thủ hợp đồng thay đổi dữ liệu của collection. |
| Lọc, ánh xạ, đếm, tìm, tổng hợp, nhóm dữ liệu | Stream API | Pipeline dễ đọc, kết hợp thao tác khai báo. |
| Đọc/ghi tệp nhị phân hoặc giao thức byte | `InputStream`, `OutputStream` | Xử lý byte và tài nguyên I/O. |
| Đọc/ghi văn bản theo charset | `Reader`/`Writer` hoặc API `Files` tương ứng | Xử lý ký tự và mã hóa. |
| Lọc hoặc tổng hợp các dòng của tệp lớn | `Files.lines` + Stream API trong `try-with-resources` | Kết hợp đọc dữ liệu theo nhu cầu và pipeline xử lý. |
| Bài toán CPU lớn cần chạy song song | Đánh giá Stream song song sau khi đo đạc | Cần nguồn có thể chia việc, hàm không can thiệp và thao tác gộp phù hợp. |

## 10. Tự kiểm tra

**Câu 1.** Sau khi gọi `List<Integer> data = List.of(1, 2, 3);` rồi `data.stream().filter(n -> n > 1);`, có bao nhiêu phần tử bị xóa khỏi `data`?

**Đáp án:** Không phần tử nào bị xóa. Chỉ mới định nghĩa pipeline; chưa có thao tác kết thúc và `filter` không sửa collection nguồn.

**Câu 2.** Vì sao đoạn `Stream<String> s = names.stream(); s.count(); s.findFirst();` không đúng?

**Đáp án:** `count()` đã tiêu thụ `s`. Muốn tìm phần tử đầu tiên, tạo Stream mới từ `names` nếu nguồn có thể duyệt lại.

**Câu 3.** Khi dùng `Files.lines(path)` để lấy 20 dòng đầu tiên, có thể bỏ `try-with-resources` vì đã dùng `limit(20)` không?

**Đáp án:** Không. `limit` có thể dừng xử lý sớm nhưng không thay thế `close` để giải phóng tài nguyên tệp.

**Câu 4.** Khi nào dùng `Iterator` có thể trực tiếp hơn dùng Stream?

**Đáp án:** Khi cần tự quyết định thời điểm gọi `next()`, kiểm soát vòng duyệt hoặc xóa phần tử trong khi duyệt qua `Iterator.remove()` nếu iterator hỗ trợ.

**Câu 5.** Tệp chứa mỗi dòng là một số nguyên. API nào chịu trách nhiệm đọc tệp và API nào chịu trách nhiệm lọc số chẵn?

**Đáp án:** `Files.lines` hoặc Reader cung cấp dữ liệu từ tệp; Stream API cung cấp `mapToInt`, `filter` và `sum` để xử lý các giá trị.

---

**Ghi nhớ:** Collection là **nơi giữ** phần tử; Iterator là **cách lấy lần lượt**; Stream API là **cách khai báo phép xử lý**; luồng I/O là **cách đưa byte/ký tự vào hoặc ra**. Khi kết hợp chúng, luôn xác định nguồn có tái sử dụng được không, pipeline đã bị tiêu thụ chưa, và có tài nguyên nào cần đóng hay không.

