# Chọn `int` hay `long` cho số đếm, chỉ số và kích thước trong Java

Trong Java, khi làm việc với **số lượng phần tử**, **chỉ số truy cập** hoặc **kích thước dữ liệu**, câu hỏi cần trả lời không chỉ là “số này có lớn không?”. Cần biết **miền giá trị lớn nhất có thể xảy ra**, **phép tính trung gian**, và **kiểu mà API Java yêu cầu**. Một mảng luôn được đánh chỉ số bằng `int`, nhưng tổng số phần tử xử lý qua nhiều mảng hoặc kích thước tệp có thể cần `long`. Chọn đúng kiểu giúp kết quả chính xác, giới hạn được kiểm tra rõ ràng và API dễ sử dụng.

## 1. Giới hạn thực tế của hai kiểu

| Thuộc tính | `int` | `long` |
| --- | --- | --- |
| Số bit biểu diễn | 32 bit, có dấu | 64 bit, có dấu |
| Giá trị nhỏ nhất | −2.147.483.648 | −9.223.372.036.854.775.808 |
| Giá trị lớn nhất | 2.147.483.647 | 9.223.372.036.854.775.807 |
| Hằng giới hạn | `Integer.MIN_VALUE`, `Integer.MAX_VALUE` | `Long.MIN_VALUE`, `Long.MAX_VALUE` |
| Literal | `100` (mặc định `int`) | `100L` (hậu tố `L`) |
| Ví dụ phù hợp | Chỉ số mảng/list, số lượng có cận trên vừa 32 bit | Tổng tích lũy lớn, byte offset, file size, thời gian/độ dài lớn khi API dùng `long` |

Cả hai đều là kiểu nguyên thủy **có dấu**. Trong bài toán số đếm và kích thước, thường chỉ cho phép giá trị không âm, nhưng việc miền âm không được dùng **không tự chuyển `int` thành kiểu 32 bit không dấu**. Giới hạn số đếm `int` vẫn là `2_147_483_647`, không phải `4_294_967_295`.

`long` có miền lớn hơn `int`, nhưng **vẫn hữu hạn**. Trong cả hai kiểu, phép `+`, `-`, `*` thông thường có thể tràn mà không ném ngoại lệ. `long` không tự giải quyết các phép tính vượt `Long.MAX_VALUE`.

**Nguyên tắc đầu tiên:** xác định giá trị lớn nhất **của từng biến và kết quả trung gian**, rồi chọn kiểu vừa miền; khi phụ thuộc một API cụ thể, phải tôn trọng kiểu tham số/giá trị trả về của API đó.

## 2. Chọn theo ý nghĩa của số: index, count, size, offset

Bốn từ thường gặp không hoàn toàn đồng nghĩa:

- **Index (chỉ số):** vị trí truy cập trong một cấu trúc, thường nằm trong `0..size-1`.
- **Count (số đếm):** số lần xảy ra/số bản ghi/số đối tượng đã xử lý; có thể tăng dần qua nhiều batch hoặc nhiều nguồn.
- **Size/length (kích thước/độ dài):** số phần tử của tập hợp, số byte của tệp, hay số đơn vị đo khác; phải xác định **đơn vị**.
- **Offset (độ dời):** vị trí tương đối so với đầu dữ liệu; một offset trong một mảng có thể là `int`, còn offset trong một tệp hàng chục GB cần `long`.

Ví dụ xử lý tuần tự 500 tệp, mỗi tệp chứa 10 triệu bản ghi: mỗi tệp có thể đọc từng phần tử bằng `int`, nhưng **tổng 5 tỷ bản ghi** vượt `Integer.MAX_VALUE` và nên tích lũy trong `long`.

### Bảng quyết định theo API và miền giá trị

| Tình huống | Kiểu nên dùng | Vì sao |
| --- | --- | --- |
| `array[index]`, vòng `for` trên mảng | `int` cho `index` | Java yêu cầu chỉ số mảng kiểu tương thích `int`; `array.length` trả `int` |
| `List.get(index)`, `List.size()` | `int` cho index/size API | Chữ ký API `get(int)` và `size()` |
| Số phần tử của cấu trúc nhỏ, có cận trên rõ và vừa `int` | `int` | Ngắn gọn, đúng miền yêu cầu |
| Tổng số phần tử qua nhiều list, batch, tệp | `long` | Tổng có thể vượt kích thước của từng list |
| `Stream.count()`, `Files.size(path)` | `long` | API trả `long` |
| Offset byte trong tệp lớn, số byte đã đọc/ghi | `long` | Byte offset có thể vượt 2 GiB |
| Số lượng quá `Long.MAX_VALUE` hoặc phép tính tổ hợp cực lớn | `BigInteger` | Vượt khả năng `long` |
| Bộ đếm cập nhật đồng thời từ nhiều luồng | `AtomicInteger`/`AtomicLong` hoặc `LongAdder` theo miền và yêu cầu | Cần xử lý concurrency riêng; chỉ đổi kiểu không tạo tính nguyên tử |

Lưu ý `Collection.size()` có kiểu trả về `int`. Hợp đồng `Collection` cho phép trả `Integer.MAX_VALUE` khi chứa nhiều hơn giới hạn đó; do vậy `size()` **không phải một API tổng quát để đo chính xác mọi tập hợp siêu lớn**. Hầu hết mảng và collection Java phổ thông đã có ràng buộc dung lượng riêng theo triển khai hoặc bộ nhớ.

## 3. Chỉ số mảng và `List`: dùng `int` vì hợp đồng API

```java
int[] prices = {120, 240, 360};

for (int i = 0; i < prices.length; i++) {
    System.out.println("prices[" + i + "] = " + prices[i]);
}
```

Biến `i` là `int` vì `prices.length` có kiểu `int` và phép truy cập mảng sử dụng chỉ số nguyên tương thích với `int`. `List.get(int index)` cũng sử dụng `int`.

Không thể dùng `long` trực tiếp làm chỉ số mảng:

```java
int[] values = {5, 10};
long index = 1L;
// int value = values[index]; // Không biên dịch: long không phải kiểu chỉ số mảng hợp lệ.
int value = values[Math.toIntExact(index)]; // Hợp lệ khi index nằm trong miền int.
```

`Math.toIntExact` chỉ kiểm tra `long` có vừa miền `int` hay không; **chưa kiểm tra index hợp lệ với mảng**. Vẫn cần `0 <= index && index < values.length` trước khi truy cập. Nếu index bằng 100 nhưng mảng có 2 phần tử, chuyển kiểu thành công nhưng truy cập vẫn ném `ArrayIndexOutOfBoundsException`.

Một mảng Java không trở thành mảng có hơn 2 tỷ chỉ số chỉ vì biến chỉ số được đổi thành `long`. `array.length` có kiểu `int`; kích thước mảng khả dụng còn bị giới hạn bởi triển khai JVM, bộ nhớ và overhead. Nếu dữ liệu cần nhiều phần tử hơn mức có thể lưu trong một mảng, hãy cân nhắc **chia đoạn (segmentation)**, xử lý bằng luồng/batch, lưu trữ trên đĩa hoặc cấu trúc chuyên biệt có API chỉ số `long`.

### Vòng lặp và biên an toàn

Dạng thông thường sau đúng cho mảng, kể cả khi rỗng:

```java
for (int i = 0; i < array.length; i++) {
    use(array[i]); // use(...) chỉ là lời gọi minh họa, không phải chương trình độc lập.
}
```

Điều kiện `i < array.length` kết thúc trước khi index vượt biên. Tránh `i <= array.length` vì phần tử cuối có index `length - 1`. Khi `array.length == 0`, không có index hợp lệ; `length - 1` bằng `-1` và không nên dùng để truy cập.

Không viết các vòng lặp kết thúc bằng ngưỡng `Integer.MAX_VALUE` với điều kiện `i <= Integer.MAX_VALUE` mà tăng `i++`: sau giá trị lớn nhất, `int` tràn về số âm và có thể khiến vòng lặp chạy mãi. Nếu thực sự cần duyệt bộ đếm dài hơn miền `int`, hãy dùng `long` và xác định rõ điều kiện dừng.

## 4. Tổng số đếm và kích thước có thể cần `long` dù đầu vào là `int`

Một batch có 10.000 phần tử có thể dùng `int batchSize`. Nhưng cộng số phần tử qua 500.000 batch có thể vượt `int`. Hãy xác định kiểu **của phép cộng**, không chỉ kiểu biến nhận kết quả.

### Sai lầm: gán sang `long` sau khi đã tràn

```java
int previous = 2_000_000_000;
int incoming = 500_000_000;

long wrong = previous + incoming;         // -1794967296: cộng int trước.
long correct = (long) previous + incoming; // 2500000000: cộng long.
```

Biểu thức `previous + incoming` có kiểu `int`, nên phép cộng tràn **trước khi** được gán cho `long`. Ép ít nhất một toán hạng sang `long` từ đầu; khi bộ đếm cần tăng nhiều lần, khai báo biến tích lũy là `long` và cộng trực tiếp:

```java
long totalRecords = 0;
for (int batchRecords : new int[] {1_500_000_000, 1_500_000_000}) {
    totalRecords += batchRecords;
}
// totalRecords = 3000000000
```

`totalRecords += batchRecords` dùng phép cộng `long` vì toán hạng trái là `long`. Để phát hiện tràn của chính `long` thay vì chấp nhận vòng số, dùng `Math.addExact(totalRecords, batchRecords)`.

### Sai lầm tương tự với phép nhân kích thước

```java
int rows = 70_000;
int columns = 70_000;

long wrongCells = rows * columns;             // 605032704: int đã tràn.
long correctCells = (long) rows * columns;    // 4900000000.
long checkedCells = Math.multiplyExact((long) rows, columns);
```

Trong tính dung lượng, `rows * columns`, `itemCount * bytesPerItem`, `width * height * channels` đều cần kiểm tra **kết quả trung gian**. Chẳng hạn nếu `width`, `height` là `int`, biểu thức `(long) (width * height)` vẫn quá muộn. Nếu kết quả tính bằng `long` vẫn có nguy cơ vượt giới hạn, dùng `Math.multiplyExact(long, long)` hoặc mô hình `BigInteger` phù hợp.

## 5. Chuyển đổi giữa `long` và `int` tại ranh giới API

Chuyển đổi mở rộng `int -> long` bảo toàn mọi giá trị `int`. Java thực hiện ngầm:

```java
int count = 1_000_000;
long total = count; // Không mất dữ liệu.
```

Ngược lại, chuyển hẹp `long -> int` **có thể mất dữ liệu**. Java yêu cầu cast tường minh và chỉ giữ 32 bit thấp của giá trị `long`; kết quả có thể âm hoặc nhỏ hơn rất nhiều:

```java
long size = 3_000_000_000L;
int silentlyWrong = (int) size;
System.out.println(silentlyWrong); // -1294967296
```

Dùng `Math.toIntExact(long)` khi một API yêu cầu `int` và kết quả phải được kiểm tra:

```java
long fileBytes = 3_000_000_000L;
try {
    int bytesAsInt = Math.toIntExact(fileBytes);
    System.out.println(bytesAsInt);
} catch (ArithmeticException ex) {
    System.out.println("Size does not fit int");
}
```

`Math.toIntExact` ném `ArithmeticException` nếu nằm ngoài miền `int`. Hàm này **không kiểm tra** liệu kích thước có không âm, có phù hợp giới hạn bộ nhớ, hay có nằm trong biên của một mảng/list cụ thể.

Nếu nguồn là kích thước tệp lớn nhưng thao tác yêu cầu `int` phần tử mỗi lần, cách đúng thường là **chia thành nhiều chunk** kích thước `int` hợp lệ, thay vì ép cả kích thước xuống `int`. Ví dụ dùng biến `long remainingBytes` để theo dõi tổng số byte còn lại, nhưng mỗi lần đọc một buffer với `int chunkSize`.

## 6. Kiểu trả về của Java API giúp định hướng quyết định

### Các API thường trả `int`

- `array.length`: số phần tử mảng.
- `String.length()`: số **đơn vị mã UTF-16**, không đồng nhất với số ký tự người dùng nhìn thấy.
- `List.size()`, `Collection.size()`, `Map.size()`: số lượng theo hợp đồng của API, kiểu `int`.
- `List.get(int)`, `String.charAt(int)`: tham số chỉ số `int`.

### Các API thường trả `long`

- `java.nio.file.Files.size(Path)`: kích thước tệp tính bằng byte.
- `java.io.File.length()`: độ dài bằng byte theo hợp đồng `File`.
- `java.util.stream.Stream.count()`: số phần tử của stream; giá trị trả về là `long`.
- `java.nio.channels.SeekableByteChannel.position()` và `size()`: vị trí/kích thước theo byte dưới dạng `long`.

Không đổi kiểu trả về của API chỉ vì “thường dữ liệu nhỏ”. Nếu `Files.size(path)` trả `long`, hãy giữ giá trị trong `long` cho đến khi có một ranh giới API thật sự yêu cầu kiểu khác.

Ví dụ:

```java
// Ví dụ sử dụng API (không phải chương trình độc lập):
long bytes = java.nio.file.Files.size(path); // path là Path đã được tạo.
long matches = records.stream().filter(record -> matchesRule(record)).count();
// records/matchesRule được định nghĩa trong ứng dụng.
```

Dòng `Files.size` có thể ném `IOException` và cần xử lý phù hợp. `Stream.count()` trả `long` ngay cả khi stream chỉ có vài phần tử. Đừng nhầm số **phần tử** trong stream với tổng **byte** hoặc tổng **kích thước** của các phần tử.

## 7. Hiệu năng và bộ nhớ: không mặc định dùng `long` cho mọi thứ

Với mảng các giá trị primitive, mỗi phần tử `int` mang 32 bit còn `long` mang 64 bit; mảng `long[]` thường cần khoảng gấp đôi phần lưu **phần tử** so với `int[]` có cùng độ dài. Bố cục đối tượng, padding, header và tổ chức bộ nhớ thực tế do JVM quyết định nên không suy ra tổng RAM chỉ bằng phép nhân 4 hoặc 8 byte.

Chọn `int` cho chỉ số mảng/list giữ đúng API, tránh cast liên tục và rõ ràng về miền giá trị. Chọn `long` cho tổng số lượng/dung lượng lớn giúp tránh tràn. Không nên vì tiết kiệm vài byte mà chọn `int` khi cận trên có thể vượt 2,1 tỷ; cũng không nên dùng `long` để làm chỉ số cho API vốn chỉ hỗ trợ `int`.

Với `Integer` và `Long` (wrapper), ngoài phạm vi giá trị còn có **boxing, unboxing, null và danh tính đối tượng**. Không so sánh hai wrapper bằng `==` để suy ra chúng có cùng giá trị số học; khi kiểm tra giá trị dùng `equals` hoặc chuyển về primitive có kiểm soát null.

### Bộ đếm trong môi trường đa luồng

Hai câu lệnh `count++` trên `int` và `long` đều không tự bảo đảm phép tăng nguyên tử khi nhiều luồng cùng sửa. Theo tình huống, dùng `AtomicInteger`, `AtomicLong`, `LongAdder` hoặc đồng bộ hóa. Chọn `AtomicLong` khi miền giá trị cần `long` và cần các thao tác nguyên tử rõ ràng; `LongAdder` thường phù hợp bộ đếm cập nhật tần suất cao nhưng `sum()` không phải snapshot nguyên tử trong lúc có cập nhật đồng thời. Chúng **không tự phát hiện overflow**: vẫn phải có chính sách giới hạn.

## 8. Ví dụ hoàn chỉnh Java 17+

Chương trình sau cho thấy việc phối hợp `int` cho chỉ số và `long` cho tổng số đếm, cùng cách phát hiện chuyển hẹp không an toàn.

Tạo tệp `IntOrLongDemo.java`:

```java
import java.util.List;

public class IntOrLongDemo {
    public static void main(String[] args) {
        int[] samples = {5, 10, 15};
        long total = 0;

        for (int i = 0; i < samples.length; i++) {
            total += samples[i];
        }
        System.out.println("Array length: " + samples.length);
        System.out.println("Array sum: " + total);

        int previous = 2_000_000_000;
        int incoming = 500_000_000;
        long wrong = previous + incoming;
        long correct = (long) previous + incoming;
        System.out.println("Overflow before widening: " + wrong);
        System.out.println("Widen before adding: " + correct);

        int rows = 70_000;
        int columns = 70_000;
        long cells = Math.multiplyExact((long) rows, columns);
        System.out.println("Grid cells: " + cells);

        List<String> words = List.of("Java", "int", "long");
        System.out.println("List size: " + words.size());
        System.out.println("Stream count: " + words.stream().count());

        long requestedIndex = 2L;
        int index = Math.toIntExact(requestedIndex);
        if (index >= 0 && index < samples.length) {
            System.out.println("Sample at index 2: " + samples[index]);
        }

        try {
            Math.toIntExact(3_000_000_000L);
            System.out.println("Unexpected: conversion succeeded");
        } catch (ArithmeticException ex) {
            System.out.println("Long value does not fit int");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac IntOrLongDemo.java
java IntOrLongDemo
```

Kết quả chính xác:

```text
Array length: 3
Array sum: 30
Overflow before widening: -1794967296
Widen before adding: 2500000000
Grid cells: 4900000000
List size: 3
Stream count: 3
Sample at index 2: 15
Long value does not fit int
```

Giải thích: `samples.length` và `index` dùng `int` để truy cập mảng; `total` là `long` để tích lũy an toàn hơn khi tổng tăng lớn. `wrong` cho thấy việc gán kết quả tràn sang `long` không sửa được lỗi. `Math.multiplyExact` giúp phát hiện tràn phép nhân nếu kết quả vượt khả năng `long`; `Math.toIntExact` ngăn chuyển hẹp âm thầm.

## 9. Quy trình lựa chọn trong dự án

1. **Xác định đại lượng và đơn vị:** số phần tử, số bản ghi tích lũy, số byte, thời lượng hay index? Không dùng tên biến mơ hồ như `size` nếu đang đo nhiều đơn vị khác nhau; chọn `fileSizeBytes`, `totalRecords`, `recordIndex`.
2. **Tính cận trên của giá trị lẫn biểu thức trung gian:** số lượng theo batch có thể nhỏ nhưng tổng hoặc tích có thể lớn. Với đầu vào ngoài hệ thống, phải xác thực cận trên, không mặc định “sẽ không bao giờ lớn”.
3. **Xác nhận hợp đồng API:** chỉ số mảng và `List.get` cần `int`; `Files.size` và `Stream.count` trả `long`. Hãy giữ đúng kiểu gốc của API khi có thể.
4. **Chọn kiểu lưu và kiểu tính:** `int` cho chỉ số trong cấu trúc hỗ trợ index `int`; `long` cho tổng hoặc offset có thể vượt `int`. Ép toán hạng sang `long` **trước** phép cộng/nhân nếu cần.
5. **Đặt ranh giới chuyển đổi có kiểm tra:** dùng `Math.toIntExact`, kiểm tra không âm, kiểm tra `index < length` hoặc chia thành chunk; dùng `Math.addExact`/`multiplyExact` nếu tràn là lỗi nghiệp vụ.
6. **Kiểm tra khi dữ liệu tăng hoặc đa luồng:** chọn primitive, atomic counter hay `BigInteger` dựa vào yêu cầu về miền, concurrency và tính nguyên tử; kiểm thử các giá trị gần `Integer.MAX_VALUE` và `Long.MAX_VALUE`.

### Những lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| `long total = intA + intB;` | Phép cộng đã tràn trước khi gán | `long total = (long) intA + intB;` |
| `long bytes = intCount * intBytesPerItem;` | Phép nhân chạy với `int` | `Math.multiplyExact((long) intCount, intBytesPerItem)` |
| `(int) fileSizeBytes` | Cắt bit, kết quả có thể âm | Giữ `long`, chia chunk; chỉ dùng `Math.toIntExact` khi chắc vừa |
| Dùng `long` trực tiếp cho `array[index]` | Không biên dịch | Dùng `int` và kiểm tra miền index |
| Xem `array.length` là dung lượng RAM hoặc byte | Nhầm số phần tử với byte | Ghi rõ đơn vị; tính byte có kiểm tra tràn và overhead |
| Dùng `<= array.length` | Truy cập index bằng độ dài, vượt biên | Dùng `< array.length` |
| Dùng `int` cho tổng bản ghi qua thời gian dài | Có thể overflow dù từng batch nhỏ | Dùng `long`/kiểm tra với `addExact` |
| Dùng `long` để mong mảng/list thông thường chứa tùy ý dữ liệu lớn | API và bộ nhớ vẫn giới hạn | Phân đoạn, streaming, lưu trữ ngoài bộ nhớ |

## 10. Câu hỏi tự kiểm tra

- Một `List` hiện có 500.000 phần tử, nhưng cần tính tổng số phần tử được xử lý trong nhiều năm. Kiểu nào nên dùng cho `listIndex` và `totalProcessed`? Vì sao?
- Với `int rows = 70_000`, `int cols = 70_000`, khác biệt giữa `long total = rows * cols` và `long total = (long) rows * cols` là gì?
- Vì sao `Math.toIntExact(longIndex)` chưa bảo đảm `array[index]` an toàn?
- Khi `Files.size(path)` trả 5.000.000.000 byte, có nên ép sang `int` để tạo một buffer không? Nếu không, làm thế nào để xử lý từng phần?
- Trong tác vụ nhiều luồng, đổi `int` thành `long` có ngăn được race condition không? Khi nào nên dùng `AtomicLong` hoặc `LongAdder`?

**Kết luận áp dụng:** dùng `int` khi miền giá trị đã được giới hạn và API truy cập yêu cầu `int`; dùng `long` khi tổng, kích thước hay offset có thể vượt miền `int`. Luôn kiểm tra **kiểu của phép toán trước khi gán**, giới hạn dữ liệu, và chuyển đổi giữa hai kiểu tại ranh giới API.