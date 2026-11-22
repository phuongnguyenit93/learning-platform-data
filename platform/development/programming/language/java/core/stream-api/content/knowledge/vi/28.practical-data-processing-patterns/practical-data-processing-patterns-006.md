# Chọn top N toàn cục và top N theo nhóm

> **Chương:** Mẫu xử lý dữ liệu thực tế  
> **Module:** JAVA_STREAM_API  
> **Trọng tâm:** Dùng `filter`, `sorted`, `limit` và `collect` để chọn các bản ghi đứng đầu theo một tiêu chí nghiệp vụ. Phân biệt **top N của toàn bộ tập dữ liệu** với **top N trong từng nhóm**, thiết kế thứ tự đồng hạng và nâng cấp sang collector giữ heap kích thước giới hạn khi dữ liệu lớn.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa chính xác một yêu cầu “top N”: phạm vi chọn, điều kiện lọc, thứ tự ưu tiên, tie-break, số N và cách xử lý đồng hạng.
2. Viết pipeline top N toàn cục bằng `filter(...).sorted(...).limit(n).toList()`.
3. Dùng `Collectors.groupingBy` kết hợp `collectingAndThen` để chọn top N **riêng mỗi nhóm**, không cắt mất dữ liệu của các nhóm khác.
4. Phân biệt top N có **đúng tối đa N dòng** và top N **bao gồm mọi dòng đồng hạng tại ranh giới**.
5. Phân tích chi phí sắp xếp toàn bộ với chi phí giữ heap kích thước N: thời gian, bộ nhớ, tác động của số nhóm.
6. Tự viết một collector top N bằng `PriorityQueue` có `supplier`, `accumulator`, `combiner` và `finisher` đúng hợp đồng.
7. Kiểm tra nguồn rỗng, N = 0, N âm, N lớn hơn số phần tử, dữ liệu trùng, comparator và giá trị null.
8. Đối chiếu kết quả tuần tự/song song, dùng dữ liệu tham chiếu và bất biến để phát hiện sai thứ tự, mất phần tử hoặc sai quy tắc đồng hạng.
9. Chọn cách tiếp cận phù hợp giữa Stream, collector, thuật toán top-K chuyên dụng và truy vấn giới hạn ngay tại nguồn dữ liệu.

Ví dụ dùng Java 17+, với `record` và `Stream.toList()`. `Comparator`, `groupingBy`, `PriorityQueue` và các overload của `Collector.of` có từ Java 8. Các đoạn code rời giả định những kiểu và dữ liệu được giới thiệu trước đó đã có trong cùng lớp/phương thức; các chương trình hoàn chỉnh có thể biên dịch độc lập.

---

## 1. Bài toán thực tế: top N của ai, theo tiêu chí nào?

Giả sử một hệ thống xử lý đơn hàng của nhiều danh mục. Người dùng muốn:

- **Top 3 toàn cục:** ba đơn đã thanh toán có giá trị cao nhất trong **mọi danh mục**.
- **Top 2 theo nhóm:** với **mỗi danh mục**, lấy tối đa hai đơn đã thanh toán có giá trị cao nhất.

Hai yêu cầu có thể dùng cùng dữ liệu và comparator nhưng **không cho cùng cấu trúc kết quả**.

~~~text
Tất cả đơn đã thanh toán
         |
         +------------------------------+
         |                              |
         v                              v
   TOP 3 TOÀN CỤC                TOP 2 THEO NHÓM
         |                              |
  Sắp xếp toàn bộ                 Gom theo category
         |                              |
     Lấy 3 dòng               BOOK: sắp + lấy 2
         |                     PEN : sắp + lấy 2
         v                     BAG : sắp + lấy 2
   List<Order>                         |
                                       v
                             Map<String,List<Order>>
~~~

Một sai lầm thường gặp là `limit(2)` **trước** `groupingBy` rồi tưởng rằng kết quả vẫn có hai bản ghi cho mỗi nhóm. Khi giới hạn đã cắt **toàn bộ** Stream xuống hai phần tử, những nhóm không xuất hiện trong hai phần tử ấy sẽ không được nhìn thấy.

### 1.1. Dữ liệu mẫu xuyên suốt

~~~java
import java.util.List;

record Order(
        String id,
        String category,
        long totalCents,
        boolean paid
) {}

List<Order> orders = List.of(
        new Order("O-01", "BOOK", 1_000, true),
        new Order("O-02", "PEN",    600, true),
        new Order("O-03", "BOOK", 2_100, true),
        new Order("O-04", "BOOK", 1_800, false),
        new Order("O-05", "PEN",  2_100, true),
        new Order("O-06", "BAG",    900, true),
        new Order("O-07", "BOOK", 2_100, true),
        new Order("O-08", "PEN",    100, false),
        new Order("O-09", "BAG",    500, true),
        new Order("O-10", "BAG",  2_100, true)
);
~~~

Mọi dòng có `id` duy nhất, `category` khác null, số tiền theo **cent** dạng `long`, và `paid` cho biết có được xét xếp hạng không. Trong bài này, **chỉ đơn đã thanh toán** tham gia cả hai phép top N.

| ID | Danh mục | Cent | Đã thanh toán? |
|---|---|---:|---|
| O-01 | BOOK | 1.000 | Có |
| O-02 | PEN | 600 | Có |
| O-03 | BOOK | 2.100 | Có |
| O-04 | BOOK | 1.800 | Không |
| O-05 | PEN | 2.100 | Có |
| O-06 | BAG | 900 | Có |
| O-07 | BOOK | 2.100 | Có |
| O-08 | PEN | 100 | Không |
| O-09 | BAG | 500 | Có |
| O-10 | BAG | 2.100 | Có |

Đầu ra mong đợi:

~~~text
Top 3 toàn cục, có tie-break theo ID:
  [O-03, O-05, O-07]

Top 2 riêng theo category:
  BOOK -> [O-03, O-07]
  PEN  -> [O-05, O-02]
  BAG  -> [O-10, O-06]
~~~

Có bốn đơn cùng giá trị `2_100`. Nếu chỉ chọn đúng ba dòng toàn cục, cần một quy tắc xác định đơn nào đứng trước; chúng ta sẽ dùng `id` tăng dần để xử lý đồng hạng.

---

## 2. Định nghĩa thứ tự bằng Comparator, không bằng cảm giác

Xếp hạng là một **hợp đồng so sánh**, không phải việc “Stream biết đơn nào tốt hơn”.

Trong ví dụ, tiêu chí là:

1. `totalCents` **giảm dần**: đơn có giá trị cao hơn đứng trước.
2. Nếu bằng cent, `id` **tăng dần**: cùng số tiền thì ID nhỏ hơn theo thứ tự từ điển đứng trước.

~~~java
import java.util.Comparator;

Comparator<Order> BEST_FIRST =
        Comparator.comparingLong(Order::totalCents)
                  .reversed()
                  .thenComparing(Order::id);
~~~

Kết quả `BEST_FIRST.compare(a,b)`:

- Nhỏ hơn `0`: `a` phải đứng **trước** `b`.
- Bằng `0`: comparator xem hai bản ghi cùng thứ hạng theo những trường đã chọn.
- Lớn hơn `0`: `a` đứng **sau** `b`.

Vì dữ liệu bài này bảo đảm ID duy nhất, comparator phân định được mọi cặp bản ghi khác nhau, kể cả khi cùng tiền. Trong hệ thống thực tế, cần xác thực ID duy nhất hoặc thêm khóa cuối như một số thứ tự nhập/bản ghi bất biến nếu muốn thứ tự **tổng quát và tái lập** cho những dòng có ID trùng.

### 2.1. Không dùng phép trừ để so sánh số lớn

~~~java
// KHÔNG NÊN: có thể tràn long và làm comparator sai.
// Comparator<Order> broken =
//         (a, b) -> (int) (b.totalCents() - a.totalCents());
~~~

Hai nguy cơ: phép trừ `long` có thể tràn; ép sang `int` còn làm mất phần lớn giá trị. Hãy dùng `Comparator.comparingLong` hoặc `Long.compare`.

~~~java
Comparator<Order> alsoCorrect =
        (a, b) -> {
            int byMoney = Long.compare(
                    b.totalCents(), a.totalCents()
            );
            return byMoney != 0
                    ? byMoney
                    : a.id().compareTo(b.id());
        };
~~~

Cả hai cách phù hợp với miền `long`, **không cần** trừ hai số tiền để biết thứ tự.

### 2.2. Nhất quán về đơn vị và tiêu chí

Nếu `totalCents` là số cent nguyên, việc so sánh chính xác theo `long` rất rõ ràng. Đừng đổi sang `double` để xếp hạng tiền tệ rồi chấp nhận sai số không được định nghĩa.

Nếu bài toán xếp hạng theo *doanh thu sau hoàn tiền*, *số lần mua*, *điểm đánh giá* hoặc *thời điểm tạo*, hãy **tính ra trường xếp hạng có nghĩa** trước khi chọn comparator. Không chọn theo một trường thuận tiện nhưng không phải tiêu chí nghiệp vụ.

---

## 3. Top N toàn cục bằng sorted().limit()

Cách đọc được nhiều nhất là:

~~~java
import java.util.List;

int n = 3;

List<Order> globalTop = orders.stream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(n)
        .toList();

System.out.println(globalTop.stream().map(Order::id).toList());
// [O-03, O-05, O-07]
~~~

Giải thích pipeline:

1. `filter(Order::paid)` bỏ đơn chưa thanh toán.
2. `sorted(BEST_FIRST)` xếp **toàn bộ** đơn hợp lệ theo tiền giảm rồi ID tăng.
3. `limit(n)` chỉ giữ **n phần tử đầu trong kết quả đã sắp xếp**.
4. `toList()` trả một list theo thứ tự kết quả; trên Java 16+, List này không cho chỉnh sửa cấu trúc qua API List.

`sorted` là một **stateful intermediate operation**. Nguồn có thứ tự và kết quả có thể xác định, nhưng `sorted` tổng quát cần xử lý tập đầu vào để tạo thứ tự toàn cục; `limit` đặt sau không tự bảo đảm Stream chỉ quan sát ba bản ghi.

### 3.1. Cắt trước khi sắp xếp là một bài toán khác

~~~java
List<Order> wrongTop = orders.stream()
        .filter(Order::paid)
        .limit(3)
        .sorted(BEST_FIRST)
        .toList();

System.out.println(wrongTop.stream().map(Order::id).toList());
// [O-03, O-01, O-02] — chỉ xếp ba đơn đã thanh toán đầu nguồn
~~~

Phép `limit(3)` đầu tiên loại `O-05`, `O-07` và `O-10` dù chúng có giá trị cao hơn. Câu hỏi đã chuyển thành **“sắp ba đơn đầu tiên”**, không còn **“ba đơn có tiền cao nhất toàn cục”**.

### 3.2. Lọc ở đâu?

~~~java
// Đúng mục tiêu: chỉ xếp những đơn đã thanh toán.
orders.stream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(3)
        .toList();
~~~

Nếu đổi thành:

~~~java
// Sai nếu muốn 3 đơn ĐÃ THANH TOÁN có giá trị cao nhất:
orders.stream()
        .sorted(BEST_FIRST)
        .limit(3)
        .filter(Order::paid)
        .toList();
~~~

Một đơn chưa thanh toán có thể chiếm suất top 3 **trước** khi bị lọc, khiến kết quả có ít hơn ba đơn hợp lệ hoặc bỏ sót đơn đủ điều kiện bên dưới. `filter` thường nên đặt trước `sorted` khi nó là điều kiện tham gia xếp hạng.

### 3.3. N bằng 0 hoặc lớn hơn số phần tử

~~~java
List<Order> none = orders.stream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(0)
        .toList();

System.out.println(none.isEmpty()); // true

List<Order> allPaid = orders.stream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(100)
        .toList();

// Có 8 đơn đã thanh toán trong dữ liệu mẫu.
System.out.println(allPaid.size()); // 8
~~~

`limit` trả tối đa N phần tử, **không tự tạo phần tử giả** khi N lớn hơn số lượng đầu vào. `limit(n)` ném `IllegalArgumentException` nếu N âm. Với API nghiệp vụ, kiểm tra N ngay tại biên đầu vào để thông báo dễ hiểu.

---

## 4. Top N theo nhóm: groupingBy + collectingAndThen

Top N theo danh mục cần **chia nhóm trước**, rồi mới sắp và giới hạn **bên trong từng nhóm**.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

int n = 2;

Map<String, List<Order>> topByCategory = orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        list -> list.stream()
                                .sorted(BEST_FIRST)
                                .limit(n)
                                .toList()
                )
        ));

System.out.println(
        topByCategory.get("BOOK")
                .stream().map(Order::id).toList()
); // [O-03, O-07]

System.out.println(
        topByCategory.get("PEN")
                .stream().map(Order::id).toList()
); // [O-05, O-02]

System.out.println(
        topByCategory.get("BAG")
                .stream().map(Order::id).toList()
); // [O-10, O-06]
~~~

Mô hình xử lý:

~~~text
orders.stream()
  |
  +-- filter(Order::paid)
  |
  +-- groupingBy(Order::category,
          collectingAndThen(
             toList(),                   // gom từng category
             list -> list.stream()
                         .sorted(...)
                         .limit(2)
                         .toList()        // hoàn thiện riêng nhóm
          )
      )
  |
  v
  Map<String, List<Order>>
      BOOK -> [O-03, O-07]
      PEN  -> [O-05, O-02]
      BAG  -> [O-10, O-06]
~~~

**Vị trí của `collectingAndThen` quyết định phạm vi hoàn thiện.** Vì collector này là downstream của `groupingBy`, mỗi nhóm nhận **một list trung gian**, rồi finisher chọn top N riêng cho nhóm ấy.

### 4.1. Sai lầm: limit trước groupingBy

~~~java
// SAI cho mục tiêu "top 2 mỗi danh mục":
Map<String, List<Order>> partial = orders.stream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(2)
        .collect(Collectors.groupingBy(Order::category));
~~~

Khi `limit(2)` chạy **trước** `groupingBy`, toàn bộ Stream chỉ còn hai đơn: `O-03` và `O-05`. Map không có `BAG`, mỗi nhóm chỉ có tối đa một đơn trong ví dụ. Đó là **top 2 toàn cục rồi nhóm lại**, không phải **top 2 từng nhóm**.

### 4.2. Map ngoài không có thứ tự khóa được bảo đảm

`groupingBy` mặc định không cam kết loại Map hoặc thứ tự duyệt của Map. Đừng so sánh trực tiếp chuỗi từ `Map.toString()` như một oracle cố định.

Nếu muốn thứ tự **tên danh mục tăng dần**, chọn map factory:

~~~java
import java.util.TreeMap;

Map<String, List<Order>> sortedKeys = orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
                Order::category,
                TreeMap::new,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        list -> list.stream()
                                .sorted(BEST_FIRST)
                                .limit(2)
                                .toList()
                )
        ));

System.out.println(sortedKeys.keySet());
// [BAG, BOOK, PEN]
~~~

`TreeMap` sắp **khóa nhóm**, còn danh sách trong từng nhóm được sắp bằng `BEST_FIRST`; đây là **hai loại thứ tự độc lập**.

### 4.3. Không làm lộ list mutable từ bước trung gian

Downstream `Collectors.toList()` tạo một danh sách trung gian không có bảo đảm bất biến. Tuy nhiên `list.stream().sorted(...).limit(n).toList()` trả List cuối không cho chỉnh sửa cấu trúc trên Java 16+.

Map ngoài từ `groupingBy` không bảo đảm không thể sửa. Nếu muốn công bố cả Map không thể thay đổi cấu trúc:

~~~java
Map<String, List<Order>> readOnly = Map.copyOf(topByCategory);
~~~

`Map.copyOf` là bản sao cấu trúc **nông**, không sao chép sâu các đối tượng `Order`. Trong ví dụ, `Order` là record có field primitive và `String`, vì vậy các dữ liệu dùng để sắp xếp đã ổn định.

---

## 5. Top N toàn cục và theo nhóm có quan hệ gì?

Cùng comparator, hai kết quả vẫn trả lời hai câu hỏi khác nhau.

| Thuộc tính | Top N toàn cục | Top N theo nhóm |
|---|---|---|
| Đầu vào xếp hạng | Tất cả bản ghi hợp lệ | Từng nhóm bản ghi hợp lệ |
| Kiểu kết quả | `List<Order>` | `Map<Key, List<Order>>` |
| Số dòng tối đa | N | Tối đa N cho **mỗi nhóm** |
| Có thể thiếu nhóm nhỏ? | Có, vì nhóm ấy không có ứng viên đủ cao toàn cục | Chỉ thiếu nếu nhóm không có bản ghi tham gia hoặc bị chính sách lọc loại hết |
| Vị trí `limit` | Sau `sorted` của toàn Stream | Bên trong downstream collector của nhóm |
| Cần thứ tự Map? | Không có Map | Chọn map factory nếu muốn thứ tự khóa |
| Khi nào dùng? | Bảng xếp hạng chung, top sản phẩm toàn hệ thống | Top sản phẩm theo cửa hàng, top giao dịch theo khách, top log theo service |

Ví dụ nếu có 100 nhóm và lấy top 3 mỗi nhóm, kết quả có thể lên tới **300 dòng**, chứ không phải chỉ có 3 dòng toàn hệ thống.

**Đừng tối ưu sai bài toán:** Giảm Stream xuống N dòng toàn cục trước khi nhóm có thể rất nhanh, nhưng không giữ top N của các nhóm không xuất hiện trong N dòng ấy.

---

## 6. Đồng hạng: đúng N dòng hay tất cả dòng bằng điểm ranh giới?

Trong dữ liệu mẫu có bốn đơn đã thanh toán cùng `2_100` cent:

~~~text
O-03 : 2100
O-05 : 2100
O-07 : 2100
O-10 : 2100
~~~

Hai chính sách thường gặp:

- **Top N chính xác tối đa N bản ghi:** dùng tie-break để xác định thứ tự hoàn toàn. Top 3 là `[O-03, O-05, O-07]`.
- **Top N kèm tất cả đồng hạng ở mốc N:** nếu phần tử thứ N có tiền `2_100`, cũng lấy mọi phần tử khác có đúng `2_100`. Top 3 **kèm đồng hạng** trả **bốn** bản ghi.

Không thể xem hai cách là cùng yêu cầu: một API xếp hạng có thể cho tối đa N dòng; API thi đấu/trao giải có thể cho nhiều hơn N vì đồng hạng.

### 6.1. Top N cố định: thêm tie-break có ý nghĩa

~~~java
Comparator<Order> bestFirst =
        Comparator.comparingLong(Order::totalCents)
                  .reversed()
                  .thenComparing(Order::id);

List<Order> top3 = orders.stream()
        .filter(Order::paid)
        .sorted(bestFirst)
        .limit(3)
        .toList();
~~~

Tie-break bằng ID ở đây là **quy tắc nghiệp vụ của ví dụ**. Nếu việc xếp thứ hạng thực tế ưu tiên thời điểm giao dịch sớm hơn, chất lượng đánh giá hoặc một trường phiên bản khác, hãy thay tie-break cho đúng. Không dùng thứ tự xuất hiện hay thứ tự thread như một quy tắc ẩn nếu nghiệp vụ cần kết quả tái lập.

### 6.2. Top N *bao gồm đồng hạng* tại ranh giới

Phương pháp dễ hiểu với nguồn hữu hạn:

~~~java
import java.util.List;

static List<Order> topWithTies(
        List<Order> source, int n,
        Comparator<Order> bestFirst) {

    if (n < 0) {
        throw new IllegalArgumentException("n phải >= 0");
    }
    if (n == 0) {
        return List.of();
    }

    List<Order> ranked = source.stream()
            .sorted(bestFirst)
            .toList();

    if (ranked.size() <= n) {
        return ranked;
    }

    // Điều kiện: comparator xếp totalCents giảm dần
    // làm tiêu chí chính, như BEST_FIRST trong bài.
    long threshold = ranked.get(n - 1).totalCents();

    return ranked.stream()
            .takeWhile(order -> order.totalCents() >= threshold)
            .toList();
}
~~~

Sử dụng:

~~~java
List<Order> paid = orders.stream()
        .filter(Order::paid)
        .toList();

List<Order> top3WithTies = topWithTies(
        paid, 3, BEST_FIRST
);

System.out.println(top3WithTies.stream().map(Order::id).toList());
// [O-03, O-05, O-07, O-10]
~~~

Điều kiện `takeWhile` đúng ở đây **vì danh sách đã được sắp giảm dần theo tiền làm khóa chính**. Nếu comparator xếp tiêu chí khác lên trước hoặc kết quả không còn có thứ tự, không được dùng ngưỡng `totalCents` theo cách này.

Hàm trả **tất cả các dòng cùng cent tại mốc N**, chứ không chỉ những dòng comparator coi là bằng nhau (vì comparator còn xét ID). Cần ghi rõ “đồng hạng” là **bằng điểm chính** hay **bằng toàn bộ bộ khóa so sánh**.

### 6.3. Top N kèm đồng hạng theo nhóm

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, List<Order>> withTiesByCategory =
        orders.stream()
                .filter(Order::paid)
                .collect(Collectors.groupingBy(
                        Order::category,
                        Collectors.collectingAndThen(
                                Collectors.toList(),
                                group -> topWithTies(
                                        group, 1, BEST_FIRST
                                )
                        )
                ));

System.out.println(
        withTiesByCategory.get("BOOK")
                .stream().map(Order::id).toList()
); // [O-03, O-07]
~~~

Ở BOOK, hai đơn cùng 2.100 cent; “top 1 kèm đồng hạng” trả cả hai. Khi một nhóm không đủ N phần tử, trả toàn bộ nhóm mà không tự điền bản ghi giả.

---

## 7. Xử lý N và chính sách đầu vào trước khi viết pipeline

N là tham số, không phải chi tiết kỹ thuật phụ. Nên xác định:

| Tình huống | Chính sách nên mô tả rõ |
|---|---|
| `n < 0` | Từ chối bằng `IllegalArgumentException` |
| `n == 0` | Trả danh sách rỗng; với top theo nhóm, quyết định có giữ khóa nhóm rỗng hay không |
| `n > số phần tử hợp lệ` | Trả hết phần tử hợp lệ, đúng thứ tự |
| N rất lớn | Cân nhắc giới hạn API và chi phí bộ nhớ/CPU |
| Khóa nhóm null | Từ chối hoặc ánh xạ sang khóa “không xác định” phù hợp nghiệp vụ |
| Giá trị xếp hạng thiếu | Lọc, báo lỗi hoặc chọn thứ tự xử lý null rõ ràng |
| ID trùng khi ID là tie-break | Báo dữ liệu sai hoặc bổ sung trường phân định tất định |
| Cùng điểm chính | Chọn đúng N bằng tie-break hoặc mở rộng theo chính sách đồng hạng |

Một hàm kiểm tra tái sử dụng:

~~~java
static void requireNonNegative(int n) {
    if (n < 0) {
        throw new IllegalArgumentException(
                "Giới hạn top N phải không âm: " + n
        );
    }
}
~~~

Nếu API nhận `long n` để truyền vào `limit`, kiểm tra trên `long`. Với cấu trúc heap, kích thước `PriorityQueue` là `int` nên phải xác định giới hạn kích thước phù hợp.

### 7.1. Group có nguồn rỗng

~~~java
List<Order> empty = List.of();

List<Order> global = empty.stream()
        .sorted(BEST_FIRST)
        .limit(5)
        .toList();

Map<String, List<Order>> grouped = empty.stream()
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.toList()
        ));

System.out.println(global);       // []
System.out.println(grouped.isEmpty()); // true
~~~

`groupingBy` chỉ tạo khóa cho các nhóm xuất hiện trong nguồn. Nó không tự tạo entry cho mọi danh mục mà hệ thống đã cấu hình nhưng chưa có đơn hàng.

Muốn **luôn** trả cả nhóm có 0 đơn, cần dữ liệu tập danh mục từ một nguồn tham chiếu rồi điền danh sách rỗng theo chính sách riêng. Không suy ra danh mục vắng mặt từ kết quả Stream của đơn hàng.

---

## 8. Chi phí của sorted().limit(N) toàn cục

Với `m` phần tử hợp lệ sau khi lọc:

~~~java
orders.stream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(n)
        .toList();
~~~

Đây là cách **dễ đọc, dễ chứng minh đúng**. Chi phí sắp xếp so sánh tổng quát thường khoảng **O(m log m)**, có thể cần lưu trữ O(m) phần tử ở giai đoạn sắp xếp.

`limit(n)` đứng sau `sorted` không có nghĩa hệ thống chỉ cần nhìn n phần tử đầu của nguồn. Một phần tử đứng ở cuối nguồn vẫn có thể là phần tử **lớn nhất**, nên không thể biết top N toàn cục bằng cách đọc n phần tử đầu tùy ý.

Với dữ liệu nhỏ hoặc trung bình, thuật toán này thường là điểm bắt đầu hợp lý. Khi `m` rất lớn và `n` rất nhỏ, có thể tối ưu bằng **heap giới hạn kích thước n**.

### 8.1. Sắp theo nhóm rồi limit từng nhóm

Với `g` nhóm, kích thước nhóm `m_1, m_2, ..., m_g`, tổng `m = Σ m_i`:

~~~text
groupingBy + collect(toList()) + sắp từng nhóm:
    thời gian phân nhóm: xấp xỉ O(m) trung bình với Map băm
    sắp trong nhóm:     Σ O(m_i log m_i)
    bộ nhớ nhóm:        O(m)
~~~

Nếu các nhóm gần như bằng nhau, sắp riêng từng nhóm có thể tốn ít so sánh hơn sắp toàn cục. Nhưng vẫn phải giữ danh sách đầu vào của từng nhóm trước khi giới hạn, nên có thể tốn bộ nhớ đáng kể khi `m` lớn.

Nếu chỉ cần N bản ghi tốt nhất mỗi nhóm, có thể duy trì **một heap N phần tử cho mỗi khóa nhóm** thay vì giữ toàn bộ danh sách.

---

## 9. Heap giới hạn N: ý tưởng trước khi viết collector

`PriorityQueue` có thể giữ phần tử ở đầu hàng đợi theo một comparator. Để duy trì **N bản ghi tốt nhất**, ta muốn `peek()` trả về **bản ghi tệ nhất trong N bản ghi đang giữ**.

Nếu comparator `BEST_FIRST` đặt bản ghi **tốt hơn trước** (so sánh trả âm), heap phải dùng **`BEST_FIRST.reversed()`**, tức **tệ nhất trước**.

~~~text
Mục tiêu: top 3 theo tiền giảm + ID tăng

Heap đang giữ: [2100/O-03, 1500/O-11, 1000/O-01]
peek() = 1000/O-01    (đang tệ nhất trong top 3)

Ứng viên 1800/O-12:
  1800 tốt hơn 1000 -> bỏ 1000, thêm 1800

Ứng viên 500/O-13:
  500 không tốt hơn peek -> bỏ qua
~~~

Thuật toán:

1. Nếu N = 0, không giữ phần tử nào.
2. Nếu heap chưa đủ N, thêm ứng viên.
3. Nếu heap đủ N, so ứng viên với `peek()` (đang tệ nhất).
4. Nếu ứng viên tốt hơn, loại `peek()` và thêm ứng viên.
5. Cuối cùng, lấy mọi phần tử trong heap và **sắp lại bằng `BEST_FIRST`** để trả danh sách hiển thị đúng thứ tự.

`PriorityQueue` **không duy trì thứ tự sắp xếp của mọi phần tử khi duyệt iterator**. Chỉ phần tử đầu `peek()` được bảo đảm theo comparator. Vì vậy `new ArrayList<>(heap)` **không thể** coi là danh sách top N đã sắp sẵn.

### 9.1. Độ phức tạp

Với `m` ứng viên, N dương và nhỏ:

- Mỗi lần thêm/thay trên heap kích thước N tốn **O(log N)**.
- Tổng duyệt m phần tử tốn khoảng **O(m log N)** trong trường hợp xấu nhất.
- Heap chỉ giữ **O(min(m, N))** phần tử.
- Khi hoàn thiện, sắp tối đa N phần tử tốn **O(N log N)**.

Nếu N lớn gần bằng m, lợi thế có thể giảm so với cách sắp toàn bộ. Heap có chi phí comparator, cấp phát và triển khai phức tạp hơn; cần benchmark với dữ liệu thật.

---

## 10. Chương trình hoàn chỉnh: top N bằng heap và Collector.of

Đoạn mã sau độc lập, dùng `Collector.of` để đóng gói một phép tổng hợp giữ tối đa N bản ghi. Nó phù hợp với cả Stream tuần tự và Stream song song khi mỗi nhánh có một accumulator riêng.

~~~java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.PriorityQueue;
import java.util.stream.Collector;

public class TopNHeapDemo {

    record Order(String id, String category, long totalCents) {}

    // Bản ghi đứng trước là bản ghi TỐT HƠN.
    static final Comparator<Order> BEST_FIRST =
            Comparator.comparingLong(Order::totalCents)
                      .reversed()
                      .thenComparing(Order::id);

    static final class TopNAccumulator {
        private final int limit;
        private final PriorityQueue<Order> worstFirst;

        TopNAccumulator(int limit) {
            if (limit < 0) {
                throw new IllegalArgumentException("limit < 0");
            }
            this.limit = limit;

            // peek(): bản ghi TỆ NHẤT trong các bản ghi đang giữ.
            this.worstFirst =
                    new PriorityQueue<>(BEST_FIRST.reversed());
        }

        void accept(Order candidate) {
            if (limit == 0) {
                return;
            }

            if (worstFirst.size() < limit) {
                worstFirst.offer(candidate);
                return;
            }

            Order worst = worstFirst.peek();

            // compare < 0 nghĩa là candidate xếp trước worst.
            if (BEST_FIRST.compare(candidate, worst) < 0) {
                worstFirst.poll();
                worstFirst.offer(candidate);
            }
        }

        TopNAccumulator merge(TopNAccumulator other) {
            if (this.limit != other.limit) {
                throw new IllegalArgumentException("Khác limit");
            }

            // Gộp những ứng viên tốt nhất của nhánh khác.
            // Không giữ tham chiếu tới heap của other.
            for (Order candidate : other.worstFirst) {
                accept(candidate);
            }
            return this;
        }

        List<Order> finish() {
            ArrayList<Order> result =
                    new ArrayList<>(worstFirst);
            result.sort(BEST_FIRST);
            return List.copyOf(result);
        }
    }

    static Collector<Order, TopNAccumulator, List<Order>>
    topNCollector(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n phải >= 0");
        }

        return Collector.of(
                () -> new TopNAccumulator(n),
                TopNAccumulator::accept,
                TopNAccumulator::merge,
                TopNAccumulator::finish
        );
    }

    public static void main(String[] args) {
        List<Order> data = List.of(
                new Order("A", "BOOK", 1_000),
                new Order("B", "PEN", 2_000),
                new Order("C", "BOOK", 2_000),
                new Order("D", "PEN", 500),
                new Order("E", "BAG", 3_000),
                new Order("F", "BOOK", 100)
        );

        List<Order> global = data.parallelStream()
                .collect(topNCollector(3));

        System.out.println(
                global.stream().map(Order::id).toList()
        ); // [E, B, C]
    }
}
~~~

Giải thích:

- `supplier` tạo **một `TopNAccumulator` mới** cho nhánh cần tích lũy; không dùng chung một `PriorityQueue` static.
- `accumulator` chỉ giữ N ứng viên tốt nhất được thấy trong phạm vi phần dữ liệu đã xử lý.
- `combiner` `merge` đưa các ứng viên từ trạng thái bên phải vào trạng thái bên trái, giữ N ứng viên tốt nhất của hợp hai tập.
- `finisher` chuyển heap thành list **đúng thứ tự hiển thị** và không cho sửa cấu trúc.
- Collector này **không** khai báo `CONCURRENT`, vì `PriorityQueue` không thread-safe; Stream có thể dùng nhiều container rồi gộp theo hợp đồng.

### 10.1. Vì sao gộp hai heap top N là đúng?

Giả sử `A` và `B` là hai tập/phân vùng độc lập. Nếu một phần tử `x` của A **không nằm trong top N của A**, thì trong A đã có ít nhất N phần tử xếp trước `x` theo comparator có thứ tự đầy đủ. Khi hợp với B, các phần tử ấy vẫn tồn tại. Vì thế `x` không thể bất ngờ trở thành top N của `A ∪ B`.

Do đó:

~~~text
topN(A ∪ B)
    = topN( topN(A) ∪ topN(B) )
~~~

Điều kiện quan trọng:

1. Dùng **cùng comparator và cùng N** ở mọi phần.
2. Comparator ổn định, không phụ thuộc trạng thái thay đổi.
3. Với yêu cầu **đúng N dòng**, tie-break phân định những bản ghi cần chọn; nếu nhiều đối tượng được coi là đồng hạng hoàn toàn, phải quy định rõ đại diện.
4. Không sửa dữ liệu nguồn hoặc đối tượng đang xếp hạng trong lúc thu thập.

Vì phép toán “hợp các ứng viên rồi chọn top N” có identity là tập rỗng và có tính kết hợp theo kết quả xếp hạng, collector có thể ghép các trạng thái trung gian theo nhiều cây phân vùng.

### 10.2. N bằng 0

Với `n == 0`, accumulator không nhận phần tử vào heap, `finish()` trả list rỗng. Điều này vẫn đúng và không gây lỗi `PriorityQueue` với capacity bằng 0 vì ví dụ dùng constructor theo comparator thay vì tạo với capacity `n`.

### 10.3. Không dựa vào thứ tự iterator của heap

~~~java
// SAI nếu muốn một list đã sắp:
// return new ArrayList<>(worstFirst);

// ĐÚNG:
ArrayList<Order> ranked = new ArrayList<>(worstFirst);
ranked.sort(BEST_FIRST);
return List.copyOf(ranked);
~~~

Nếu không sắp cuối, kết quả có thể chứa đủ top N nhưng vị trí hiển thị không đúng hợp đồng.

---

## 11. Dùng lại topNCollector để lấy top N theo nhóm

Điểm mạnh của việc đóng gói thành collector là có thể đặt trực tiếp vào downstream `groupingBy`:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

// Dùng kiểu Order và topNCollector từ TopNHeapDemo.
Map<String, List<Order>> topTwoByCategory = data.parallelStream()
        .collect(Collectors.groupingBy(
                Order::category,
                topNCollector(2)
        ));

System.out.println(
        topTwoByCategory.get("BOOK")
                .stream().map(Order::id).toList()
); // [C, A]

System.out.println(
        topTwoByCategory.get("PEN")
                .stream().map(Order::id).toList()
); // [B, D]

System.out.println(
        topTwoByCategory.get("BAG")
                .stream().map(Order::id).toList()
); // [E]
~~~

Đặt đoạn mã trên **trong `TopNHeapDemo.main`**, sau khi `data` đã được khai báo. Dữ liệu ví dụ trong chương trình heap có BOOK gồm `C=2.000`, `A=1.000`, `F=100`, nên top 2 là `[C,A]`.

Trong một pipeline song song, `groupingBy` có thể tạo các bản đồ trung gian rồi ghép theo khóa. Với mỗi khóa, `TopNAccumulator.merge` xử lý gộp ứng viên của nhóm tương ứng. Không dùng một heap **toàn cục** cho mọi khóa nếu yêu cầu là top N **mỗi nhóm**.

### 11.1. Bộ nhớ top N theo nhóm

Nếu có `g` nhóm và mỗi nhóm giữ tối đa `n` bản ghi, phần heap top N có thể giữ tối đa **O(g·n)** tham chiếu (hoặc ít hơn nếu nhóm nhỏ). Cần cộng thêm chi phí Map và các đối tượng trung gian khi chạy song song.

Đối với `n` nhỏ và các nhóm rất lớn, đây là điểm mạnh so với việc giữ đầy đủ `List<Order>` của từng nhóm. Nhưng nếu số nhóm `g` cực lớn (gần bằng số bản ghi), bộ nhớ cho Map và heap của từng nhóm vẫn có thể đáng kể.

### 11.2. Không tự đánh dấu CONCURRENT

`PriorityQueue` không bảo đảm an toàn khi nhiều thread cùng `offer`/`poll` trên **một instance**. Collector top N trong ví dụ là kiểu thông thường, không công bố `CONCURRENT`.

Điều này **không** ngăn dùng `parallelStream()`: Stream có thể tích lũy vào các container độc lập và dùng combiner ghép chúng. Nếu muốn collector concurrent thật sự, phải thiết kế lại container và hợp đồng đồng thời; không chỉ gắn thêm một `Characteristic`.

---

## 12. So sánh các cách triển khai

| Giải pháp | Độ dễ hiểu | Bộ nhớ thêm điển hình | Khi phù hợp |
|---|---|---|---|
| `sorted().limit(n)` toàn cục | Rất cao | Có thể O(m) cho sort | Dữ liệu nhỏ/vừa, ưu tiên mã rõ ràng |
| `groupingBy(..., collectingAndThen(toList(), sort + limit))` | Cao | O(m) để giữ các nhóm | Bài toán top N theo nhóm vừa phải |
| `collect(topNCollector(n))` | Trung bình | O(min(m,n)) cho heap | N nhỏ, nhiều ứng viên, muốn kiểm soát bộ nhớ |
| `groupingBy(..., topNCollector(n))` | Trung bình | O(g·n) + Map | N nhỏ cho mỗi nhóm, nhiều dữ liệu mỗi nhóm |
| Lấy top N từ tầng truy vấn dữ liệu | Phụ thuộc DB/nguồn | Tránh chuyển dư thừa nhiều dòng vào Java | Nguồn dữ liệu rất lớn, đã có cơ chế sort/limit/index/window function |
| Thuật toán chọn khác (quickselect, specialized top-K) | Cao hơn | Phụ thuộc thuật toán | Cần tối ưu đặc thù sau khi đo |

Trong bảng, `m` là số bản ghi sau lọc và `g` là số nhóm. Những biểu thức độ phức tạp là **mô hình điển hình**, không phải cam kết runtime của mọi JDK hoặc mọi implementation `Spliterator`.

**Không phải cứ thuật toán có O(m log n) là nhanh hơn trong thực tế.** Comparator phức tạp, chi phí tạo heap mỗi nhóm, allocation, GC và overhead song song đều cần đo bằng benchmark có thiết kế đúng.

---

## 13. Chọn top N theo điểm tổng hợp của nhóm, không phải top N bản ghi trong nhóm

Hai bài toán khác nhau:

1. **Top N bản ghi mỗi nhóm:** với từng category, chọn N Order giá trị cao nhất.
2. **Top N nhóm theo tổng doanh thu:** cộng doanh thu của từng category, sau đó chọn N category có tổng cao nhất.

Bài toán thứ hai cần **grouping/reduction trước khi xếp hạng nhóm**, không dùng `topNCollector<Order>` cho từng nhóm.

~~~java
import java.math.BigInteger;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, BigInteger> totalByCategory = orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.mapping(
                        order -> BigInteger.valueOf(order.totalCents()),
                        Collectors.reducing(
                                BigInteger.ZERO,
                                BigInteger::add
                        )
                )
        ));

Comparator<Map.Entry<String, BigInteger>> groupRanking =
        Map.Entry.<String, BigInteger>comparingByValue(
                        Comparator.reverseOrder()
                )
                .thenComparing(Map.Entry::getKey);

List<Map.Entry<String, BigInteger>> bestGroups =
        totalByCategory.entrySet().stream()
                .sorted(groupRanking)
                .limit(2)
                .toList();

System.out.println(
        bestGroups.stream()
                .map(Map.Entry::getKey)
                .toList()
); // [BOOK, BAG]
~~~

Trong dữ liệu đầu bài:

~~~text
BOOK: 1000 + 2100 + 2100 = 5200
BAG :  900 +  500 + 2100 = 3500
PEN :  600 + 2100        = 2700
~~~

Vì `BigInteger::add` là phép cộng nguyên chính xác, không có overflow `long` trong giai đoạn gộp. Nếu dùng `Collectors.summingLong`, vẫn phải kiểm tra miền tổng có thể vượt `long` hay không.

**Đừng nhầm:** top 2 nhóm theo tổng doanh thu trả `[BOOK,BAG]`; nó **không** trả top 2 đơn hàng của mỗi nhóm.

### 13.1. Có thể dùng teeing hoặc summarizing khi cần nhiều thống kê

Nếu tiêu chí chọn nhóm dựa trên **tổng doanh thu, số đơn và trung bình**, có thể dùng một downstream collector chứa các thống kê đó. Sau khi đã có một giá trị thống kê cho mỗi nhóm, ta mới sắp theo **quy tắc ưu tiên của nhóm**.

Đây là trường hợp phối hợp các chủ đề `groupingBy`, `reducing`, collector nhiều tầng và độ chính xác của tổng số trong Java Stream API.

---

## 14. Null, dữ liệu trùng và tính bất biến

### 14.1. category hoặc ID null

~~~java
// groupingBy(Order::category) yêu cầu classifier trả khóa khác null
// trong cách sử dụng thông thường.
//
// Comparator.thenComparing(Order::id) cũng cần một chính sách
// xử lý id null rõ ràng.
~~~

Trong dữ liệu thực tế, cần quyết định:

- **Từ chối** đơn hàng không có category hoặc ID.
- **Loại bỏ** bản ghi thiếu dữ liệu, nếu đúng yêu cầu báo cáo.
- **Gom vào khóa đại diện** cho category chưa biết và phân biệt với tên category hợp lệ.
- **Sắp null theo một thứ tự đã quy định** bằng comparator hỗ trợ null, nếu null được phép trong ranking.

Không dùng một giá trị sentinel tùy tiện có thể trùng với khóa thật. `groupingBy` thường không cho classifier trả null; `List.copyOf`/`Map.copyOf` cũng từ chối null.

### 14.2. distinct() không tương đương “mỗi ID một lần”

~~~java
record Order(String id, String category, long totalCents, boolean paid) {}
~~~

Hai Order cùng `id` nhưng khác `totalCents` là **hai record khác nhau theo `equals`**. `stream.distinct()` không tự loại một bản ghi theo ID.

Nếu nguồn có nhiều phiên bản cùng ID, nên **khử trùng theo ID theo quy tắc version/timestamp** trước khi xếp hạng, chẳng hạn `Collectors.toMap` với merge function chọn bản ghi mới nhất. Phải xử lý ID trùng theo chính sách rõ ràng, không tự chọn tùy thứ tự xử lý trong parallel stream.

### 14.3. Chọn top N theo snapshot

Nếu các `Order` mutable thay đổi `totalCents` trong lúc so sánh, comparator có thể trả kết quả không nhất quán. Điều đó có thể phá thứ tự sort hoặc làm heap loại nhầm bản ghi.

Trong ví dụ, `record Order` chứa các kiểu `String`, `long`, `boolean` nên trạng thái dùng xếp hạng là bất biến. Với entity mutable từ cơ sở dữ liệu hoặc cache, hãy chụp snapshot DTO bất biến trước khi thu thập, hoặc bảo đảm không có cập nhật cạnh tranh.

`List.copyOf` chỉ đóng băng **cấu trúc danh sách**, không tự sao chép sâu một entity mutable.

---

## 15. Parallel stream: kết quả đúng trước, tốc độ sau

Top N đặt các ràng buộc đáng chú ý lên phép xử lý song song:

- `sorted` là thao tác có trạng thái, cần thứ tự **toàn cục**.
- `limit` trên Stream **ORDERED** phải chọn đúng tiền tố sau khi sắp.
- `groupingBy` có thể tạo nhiều Map trung gian và gộp chúng theo khóa.
- Collector heap có thể dễ chia/gộp nếu `combiner` đúng, nhưng vẫn phải cấp phát/gộp nhiều heap.
- Việc `PriorityQueue` không thread-safe không phải lỗi nếu nó chỉ được sửa trong container riêng và collector **không** khai báo `CONCURRENT`.

~~~java
List<Order> sequential = orders.stream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(3)
        .toList();

List<Order> parallel = orders.parallelStream()
        .filter(Order::paid)
        .sorted(BEST_FIRST)
        .limit(3)
        .toList();

if (!sequential.equals(parallel)) {
    throw new AssertionError("Top toàn cục sai thứ tự/kết quả");
}
~~~

Với List có encounter order và comparator phân định rõ thứ tự, hai cách phải cho top 3 đúng theo hợp đồng. Nhưng **chỉ so tuần tự và song song vẫn chưa đủ**: nếu comparator sai tiêu chí nghiệp vụ, cả hai có thể cùng sai. Cần bộ dữ liệu có kết quả kỳ vọng độc lập.

### 15.1. Có thể bỏ encounter order bằng unordered()?

Đối với **top N theo thứ tự xếp hạng rõ ràng**, thường không cần `unordered()`. `sorted(BEST_FIRST)` đặt ra thứ tự kết quả mới; tuy nhiên việc bỏ encounter order **trước đó** có thể làm thay đổi cách xử lý các trường hợp đồng hạng nếu comparator không phân định đầy đủ.

Nếu yêu cầu **top N bản ghi có tie-break cố định**, hãy viết comparator giải quyết đồng hạng, thay vì hy vọng `unordered()` giúp nhanh hơn mà không đổi kết quả.

### 15.2. Top theo nhóm và Map.equals

~~~java
Map<String, List<Order>> seq = orders.stream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        xs -> xs.stream().sorted(BEST_FIRST)
                                .limit(2).toList()
                )
        ));

Map<String, List<Order>> par = orders.parallelStream()
        .filter(Order::paid)
        .collect(Collectors.groupingBy(
                Order::category,
                Collectors.collectingAndThen(
                        Collectors.toList(),
                        xs -> xs.stream().sorted(BEST_FIRST)
                                .limit(2).toList()
                )
        ));

if (!seq.equals(par)) {
    throw new AssertionError("Top theo nhóm không tương đương");
}
~~~

`Map.equals` so các ánh xạ theo nội dung, không phụ thuộc thứ tự duyệt khóa Map. `List.equals` vẫn xét thứ tự phần tử **bên trong từng nhóm** — đúng với hợp đồng top N đã sắp.

---

## 16. Kiểm chứng top N bằng bất biến

Bên cạnh so với kết quả tính tay, có thể kiểm tra các bất biến:

| Bất biến | Kiểm tra |
|---|---|
| Kích thước | `result.size() == min(n, số bản ghi đủ điều kiện)` với top N cố định |
| Tính hợp lệ | Mọi Order trong kết quả đều thỏa điều kiện `paid` và quy tắc lọc |
| Thứ tự | Không có cặp kề nhau `a,b` với `BEST_FIRST.compare(a,b) > 0` |
| Đúng mức ưu tiên | Không có bản ghi bị bỏ có thứ hạng cao hơn bản ghi cuối trong top N |
| Không mất/nhân đôi | Kết quả chứa đúng những phần tử nguồn được chọn, theo multiplicity/định danh đã quy định |
| Nhóm đúng | Mọi phần tử trong `map.get(category)` có category tương ứng |
| N theo mỗi nhóm | Mỗi List chứa tối đa N dòng, độc lập nhóm khác |
| N = 0 | Top toàn cục rỗng; top theo nhóm theo chính sách khóa đã nêu |
| Đồng hạng | Kết quả tuân thủ chính sách đúng N hoặc bao gồm mọi đồng hạng ở ngưỡng |
| Song song | Cùng hợp đồng với tuần tự/oracle trên snapshot bất biến |

### 16.1. Helper kiểm tra thứ tự

~~~java
import java.util.Comparator;
import java.util.List;

static <T> void requireSorted(
        List<T> result, Comparator<? super T> bestFirst) {

    for (int i = 1; i < result.size(); i++) {
        if (bestFirst.compare(
                result.get(i - 1), result.get(i)
        ) > 0) {
            throw new AssertionError(
                    "Sai thứ tự tại vị trí " + i
            );
        }
    }
}
~~~

Có thể gọi:

~~~java
requireSorted(globalTop, BEST_FIRST);
for (List<Order> group : topByCategory.values()) {
    requireSorted(group, BEST_FIRST);
}
~~~

Hàm này kiểm tra thứ tự đầu ra, **không chứng minh đã chọn đúng phần tử**. Một List gồm ba phần tử có tiền thấp vẫn có thể được sắp đúng; cần thêm oracle và kiểm tra không bỏ qua ứng viên tốt hơn.

### 16.2. Kiểm chứng bằng kết quả tính tay

Với dữ liệu mẫu, ta biết trước:

~~~text
Top 3 toàn cục: [O-03, O-05, O-07]
Top 2 BOOK:    [O-03, O-07]
Top 2 PEN:     [O-05, O-02]
Top 2 BAG:     [O-10, O-06]
~~~

Kiểm tra các ID ở đúng vị trí để phát hiện cả sai thứ tự tie-break lẫn sai tiêu chí. Khi dùng `Map`, lấy theo khóa thay vì tin vào thứ tự duyệt.

### 16.3. So sánh với oracle độc lập

Với một thuật toán heap mới, có thể dùng pipeline `sorted().limit()` làm **oracle tham chiếu** vì nó đơn giản và minh bạch. Tuy nhiên comparator vẫn phải được kiểm tra độc lập với yêu cầu nghiệp vụ; dùng cùng một comparator sai ở cả hai cách có thể cho PASS giả.

Ngoài việc so heap với sort, hãy thêm trường hợp đã tính tay, các giá trị gần giới hạn `long` và ca đồng hạng để bảo đảm tính đúng theo nghiệp vụ.

---

## 17. Chương trình hoàn chỉnh: top toàn cục và theo nhóm

Mẫu sau tách việc xác thực N, chọn top toàn cục và chọn top trong từng nhóm thành những hàm rõ ràng. Tệp Java độc lập có thể chạy với Java 17+.

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class TopNStreamDemo {

    record Order(
            String id,
            String category,
            long totalCents,
            boolean paid
    ) {}

    static final Comparator<Order> BEST_FIRST =
            Comparator.comparingLong(Order::totalCents)
                      .reversed()
                      .thenComparing(Order::id);

    static void requireN(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("N phải >= 0");
        }
    }

    static List<Order> globalTop(List<Order> orders, int n) {
        requireN(n);

        return orders.stream()
                .filter(Order::paid)
                .sorted(BEST_FIRST)
                .limit(n)
                .toList();
    }

    static Map<String, List<Order>> topByCategory(
            List<Order> orders, int n) {
        requireN(n);

        Map<String, List<Order>> result = orders.stream()
                .filter(Order::paid)
                .collect(Collectors.groupingBy(
                        Order::category,
                        Collectors.collectingAndThen(
                                Collectors.toList(),
                                group -> group.stream()
                                        .sorted(BEST_FIRST)
                                        .limit(n)
                                        .toList()
                        )
                ));

        // Map và List trả về không cho sửa cấu trúc.
        return Map.copyOf(result);
    }

    static List<String> ids(List<Order> selected) {
        return selected.stream().map(Order::id).toList();
    }

    static void requireIds(
            List<Order> selected, String... expected) {
        List<String> actual = ids(selected);
        List<String> target = List.of(expected);

        if (!actual.equals(target)) {
            throw new AssertionError(
                    "Expected " + target + ", got " + actual
            );
        }
    }

    public static void main(String[] args) {
        List<Order> data = List.of(
                new Order("O-01", "BOOK", 1_000, true),
                new Order("O-02", "PEN",    600, true),
                new Order("O-03", "BOOK", 2_100, true),
                new Order("O-04", "BOOK", 1_800, false),
                new Order("O-05", "PEN",  2_100, true),
                new Order("O-06", "BAG",    900, true),
                new Order("O-07", "BOOK", 2_100, true),
                new Order("O-08", "PEN",    100, false),
                new Order("O-09", "BAG",    500, true),
                new Order("O-10", "BAG",  2_100, true)
        );

        List<Order> global = globalTop(data, 3);
        requireIds(global, "O-03", "O-05", "O-07");

        Map<String, List<Order>> grouped =
                topByCategory(data, 2);
        requireIds(grouped.get("BOOK"), "O-03", "O-07");
        requireIds(grouped.get("PEN"), "O-05", "O-02");
        requireIds(grouped.get("BAG"), "O-10", "O-06");

        if (!globalTop(data, 0).isEmpty()) {
            throw new AssertionError("N=0 phải rỗng");
        }

        if (globalTop(data, 100).size() != 8) {
            throw new AssertionError("Sai số đơn đã thanh toán");
        }

        if (!globalTop(List.of(), 5).isEmpty()
                || !topByCategory(List.of(), 5).isEmpty()) {
            throw new AssertionError("Nguồn rỗng phải rỗng");
        }

        System.out.println("GLOBAL " + ids(global));
        System.out.println("BOOK   " + ids(grouped.get("BOOK")));
        System.out.println("PEN    " + ids(grouped.get("PEN")));
        System.out.println("BAG    " + ids(grouped.get("BAG")));
        System.out.println("TOP_N_OK");
    }
}
~~~

Kết quả kỳ vọng:

~~~text
GLOBAL [O-03, O-05, O-07]
BOOK   [O-03, O-07]
PEN    [O-05, O-02]
BAG    [O-10, O-06]
TOP_N_OK
~~~

**Giới hạn của ví dụ:** Chương trình minh họa dữ liệu tin cậy, ID duy nhất và category không null. Trong ứng dụng có dữ liệu từ API hoặc cơ sở dữ liệu, cần xác thực/chuẩn hóa các trường và định nghĩa chính sách cập nhật nguồn trước khi công bố chỉ mục/top N.

---

## 18. Những sai lầm phổ biến và cách tìm phản ví dụ

| Sai lầm | Phản ví dụ ngắn | Cách sửa |
|---|---|---|
| `limit(N)` trước `sorted` | `[2,9,7]`, N=1: lấy 2 thay vì 9 | Sắp toàn bộ ứng viên rồi mới limit |
| `limit(N)` trước `groupingBy` | Hai dòng toàn cục thuộc BOOK/PEN, BAG biến mất | Đặt limit trong downstream của nhóm |
| `filter(paid)` sau `limit` | Đơn chưa thanh toán chiếm suất rồi bị loại | Lọc điều kiện tham gia trước khi xếp |
| Không có tie-break | Nhiều đơn cùng điểm ở ranh giới | Xác định quy tắc phụ và dữ liệu duy nhất |
| Comparator dùng phép trừ | Giá trị gần `Long.MAX_VALUE`/`MIN_VALUE` | `comparingLong` hoặc `Long.compare` |
| Dùng `distinct()` để khử ID trùng | Hai record cùng ID nhưng khác tiền vẫn tồn tại | Khử theo khóa/phiên bản bằng `toMap` đúng chính sách |
| Quên sắp list lấy từ heap | `PriorityQueue.iterator` không trả toàn bộ theo thứ tự ưu tiên | Sort bằng `BEST_FIRST` trong finisher |
| Heap dùng comparator tốt-nhất-trước | `peek()` là tốt nhất; thay nhầm phần tử | Dùng `BEST_FIRST.reversed()` để `peek()` là tệ nhất |
| Combiner chỉ trả heap trái | Mất ứng viên tốt ở phân vùng phải | Hợp top N của hai nhánh |
| Dùng chung `PriorityQueue` cho mọi thread | Race condition và dữ liệu hỏng | Supplier độc lập, collector không CONCURRENT |
| Chọn đúng N khi cần mọi đồng hạng | 4 dòng cùng điểm cao nhất, top3 bỏ một dòng | Dùng ngưỡng điểm N, mở rộng kết quả |
| Dựa vào thứ tự `HashMap` | Nhóm in ra mỗi lần khác | `TreeMap` hoặc sắp danh sách khóa |
| N âm hoặc vượt giới hạn | `limit(-1)` lỗi; heap với capacity sai | Kiểm tra N tại biên |
| Nguồn đang bị sửa | Điểm hoặc category đổi lúc tính | Snapshot bất biến, đồng bộ nguồn |
| So sequential và parallel mà không có oracle | Hai chế độ có cùng comparator sai | Thêm kết quả tính tay và bất biến |

---

## 19. Kiểm thử với dữ liệu lớn và chạy song song

Ngoài các ca đã tính tay, cần thử những mẫu dữ liệu có khả năng làm lộ lỗi heap và combiner:

1. **Một nhóm rất lớn:** N nhỏ, nhiều ứng viên, heap phải thay `peek()` thường xuyên.
2. **Rất nhiều nhóm nhỏ:** kích thước nhóm nhỏ hơn N, toàn bộ phần tử nhóm phải được giữ.
3. **Tất cả điểm bằng nhau:** comparator tie-break phải chọn đúng những ID được ưu tiên.
4. **Điểm âm/dương và giá trị cực trị `long`:** comparator không được tràn.
5. **Dữ liệu đảo thứ tự:** bản ghi lớn nhất ở cuối, không được cắt sớm trước khi nhìn thấy.
6. **N = 0, N = 1, N = số phần tử, N lớn hơn số phần tử**.
7. **Nguồn rỗng và nhóm không có bản ghi paid**.
8. **Nhiều lượt `parallelStream`:** kết quả phải khớp oracle, bất kể cách chia công việc.
9. **Khóa nhóm và ID trùng hoặc null:** xử lý đúng theo chính sách đã định, không im lặng trả kết quả thiếu.
10. **Khác phân bố nhóm:** một category có rất nhiều bản ghi, category khác rất ít để thử gộp không cân bằng.

### 19.1. Đối chiếu heap với sorted.limit trên cùng dữ liệu

Với `TopNHeapDemo` ở mục 10, thêm mã sau vào `main`:

~~~java
List<Order> bySorting = data.stream()
        .sorted(BEST_FIRST)
        .limit(3)
        .toList();

List<Order> byHeap = data.parallelStream()
        .collect(topNCollector(3));

if (!bySorting.equals(byHeap)) {
    throw new AssertionError(
            "Heap khác sorted oracle"
    );
}
~~~

Đây là phép đối chiếu hai thuật toán có cấu trúc khác nhau. Nhưng vì chúng dùng **cùng comparator**, vẫn cần kiểm thử comparator theo dữ liệu nhỏ đã tính tay để tránh cả hai cùng mắc lỗi xếp hạng.

### 19.2. Kiểm tra top N theo nhóm bằng bất biến

~~~java
// Dùng Map<String,List<Order>> topByCategory ở mục 4.
for (Map.Entry<String, List<Order>> entry
        : topByCategory.entrySet()) {

    String group = entry.getKey();
    List<Order> ranked = entry.getValue();

    if (ranked.size() > 2) {
        throw new AssertionError("Vượt quá N ở nhóm " + group);
    }

    for (Order order : ranked) {
        if (!order.paid() || !group.equals(order.category())) {
            throw new AssertionError(
                    "Bản ghi không thuộc nhóm " + group
            );
        }
    }

    requireSorted(ranked, BEST_FIRST);
}
~~~

Phép kiểm này xác nhận số lượng, dữ liệu hợp lệ và thứ tự. Để xác nhận **tính tối ưu**, còn cần kiểm tra không có ứng viên bị bỏ nào trong cùng nhóm xếp trước phần tử cuối đã chọn.

### 19.3. Benchmark đúng vấn đề

Nên đo với JMH hoặc benchmark được kiểm soát, thử biến số:

| Biến | Giá trị cần thử |
|---|---|
| Tổng số ứng viên m | Nhỏ, trung bình, rất lớn |
| N | 0, 1, 10, 100, gần m |
| Số nhóm g | Ít nhóm lớn, nhiều nhóm nhỏ |
| Tỷ lệ paid | Thấp và cao |
| Phân bố điểm | Gần như không trùng, nhiều đồng hạng |
| Loại nguồn | `ArrayList`, nguồn có `Spliterator` khó chia |
| Chế độ | Sequential và parallel |
| Thuật toán | Sắp toàn bộ vs heap giới hạn |
| Chi phí | Thời gian, memory allocation, GC, peak memory |

Đừng đưa thời gian tạo dữ liệu lớn vào vùng đo nếu mục tiêu chỉ là so sánh **chọn top N**. Cũng đừng chỉ in `System.nanoTime()` của một lần chạy rồi kết luận thuật toán nào nhanh hơn: JIT warm-up, tải CPU, GC và cách kết quả được sử dụng đều có thể làm sai số đo.

---

## 20. Bài tập nền tảng (kèm đáp án)

### Bài 1. Top 2 toàn cục

**Đề:** Cho các điểm `[40, 90, 60, 90]`, chọn hai điểm lớn nhất theo thứ tự giảm dần.

**Đáp án:**

~~~java
import java.util.Comparator;
import java.util.List;

List<Integer> top = List.of(40, 90, 60, 90)
        .stream()
        .sorted(Comparator.reverseOrder())
        .limit(2)
        .toList();

System.out.println(top); // [90, 90]
~~~

Hai giá trị `90` vẫn xuất hiện hai lần vì bài toán là top **bản ghi/giá trị của từng vị trí**, không phải tập giá trị duy nhất.

### Bài 2. Sai vị trí limit

**Đề:** Với `[40,90,60]` và N=1, `limit(1).sorted(reverseOrder())` trả gì?

**Đáp án:** Trả `[40]`, vì chỉ sắp một phần tử đầu. Top 1 toàn cục đúng là `[90]`. Phải đặt `sorted` trước `limit`.

### Bài 3. Top N theo nhóm

**Đề:** Các đơn thuộc BOOK có điểm `[5,9,1]`, PEN có điểm `[2,7,6]`. Top 2 mỗi nhóm là gì?

**Đáp án:** BOOK `[9,5]`, PEN `[7,6]`. Mỗi nhóm được sắp và giới hạn **riêng**; không giới hạn toàn bộ nguồn trước khi nhóm.

### Bài 4. N bằng 0

**Đề:** `limit(0)` và collector heap trong bài trả gì?

**Đáp án:** Cả hai trả danh sách rỗng. Với `groupingBy`, nếu vẫn xử lý các bản ghi theo khóa trước khi hoàn thiện, các khóa nhóm có thể tồn tại và ánh xạ tới danh sách rỗng; cần quyết định chính sách kết quả của API.

### Bài 5. N lớn hơn số phần tử

**Đề:** Một nhóm chỉ có ba bản ghi, N=10. Phải trả bao nhiêu bản ghi?

**Đáp án:** Trả ba bản ghi đã được sắp theo comparator, không thêm bảy bản ghi giả.

### Bài 6. Comparator không tràn

**Đề:** Vì sao `(int)(b.totalCents()-a.totalCents())` nguy hiểm?

**Đáp án:** Phép trừ `long` có thể tràn và ép về `int` có thể mất thông tin. Dùng `Comparator.comparingLong(Order::totalCents).reversed()` hoặc `Long.compare(b.totalCents(), a.totalCents())`.

### Bài 7. Top N và distinct

**Đề:** Hai giao dịch cùng giá trị `100` nhưng khác ID. Có tự động dùng `distinct()` để chỉ giữ một giao dịch không?

**Đáp án:** Không. Nếu yêu cầu top N **giao dịch**, hai dòng khác ID vẫn là hai giao dịch. `distinct()` dùng `equals` của đối tượng, không phải “loại mọi điểm bằng nhau”.

### Bài 8. Đồng hạng tại ranh giới

**Đề:** Điểm `[100, 90, 90, 70]`, N=2. Top N đúng số dòng và top N kèm đồng hạng khác nhau thế nào?

**Đáp án:** Đúng hai dòng trả `[100,90]` theo tie-break; kèm đồng hạng ở ngưỡng 90 trả `[100,90,90]`, tức ba dòng.

---

## 21. Bài tập trung cấp (kèm đáp án)

### Bài 9. Chọn comparator cho top doanh thu

**Đề:** `Order` có `totalCents` dạng `long`, `id` là chuỗi duy nhất. Viết comparator theo cent giảm, ID tăng.

**Đáp án:**

~~~java
Comparator<Order> bestFirst =
        Comparator.comparingLong(Order::totalCents)
                  .reversed()
                  .thenComparing(Order::id);
~~~

Tiêu chí ID tránh việc các đơn cùng cent bị chọn phụ thuộc tình cờ thứ tự đầu vào nếu top N chỉ giữ một phần trong số các đơn đồng hạng.

### Bài 10. Vì sao heap cần worst-first?

**Đề:** Heap có giới hạn N=3 và ba bản ghi đang giữ có điểm 20, 15, 10. Khi điểm 17 đến, cần bỏ điểm nào?

**Đáp án:** Bỏ điểm 10 và thêm điểm 17. `peek()` nên là điểm 10, tức **tệ nhất** trong top 3 hiện tại. Vì thế dùng comparator **ngược** với thứ tự hiển thị tốt nhất trước.

### Bài 11. Gộp hai heap có mất ứng viên tốt không?

**Đề:** Phân vùng A có `[100,90,10]`, B có `[95,80,5]`, N=2. Top 2 mỗi phần và top 2 sau gộp là gì?

**Đáp án:** Top A `[100,90]`, top B `[95,80]`. Gộp các ứng viên này và chọn top 2 cho ra `[100,95]`. Các giá trị 10 và 5 không thể vào top 2 toàn cục vì ngay trong phân vùng của chúng đã có hai giá trị tốt hơn.

### Bài 12. Top 1 mỗi nhóm không phải top 1 toàn cục

**Đề:** BOOK có đơn 100, PEN có đơn 90, BAG có đơn 80. Top 1 theo nhóm trả bao nhiêu bản ghi?

**Đáp án:** Trả ba bản ghi trong ba list tương ứng. Top 1 toàn cục mới chỉ trả đơn 100. Không đặt `limit(1)` trước `groupingBy`.

### Bài 13. Top nhóm theo tổng doanh thu

**Đề:** BOOK có hai đơn 100 và 200; PEN có một đơn 250. Chọn nhóm đứng đầu theo **tổng** tiền, không theo đơn tiền lớn nhất.

**Đáp án:** BOOK đứng đầu vì tổng 300 lớn hơn PEN 250, dù đơn lớn nhất của PEN (250) lớn hơn từng đơn riêng của BOOK. Dùng `groupingBy` + `reducing/summing` trước rồi `sorted` trên entry của Map.

### Bài 14. Top 2 đồng hạng

**Đề:** Sau khi sắp theo điểm giảm, danh sách là `[120/A, 110/B, 110/C, 90/D]`. N=2 và cần bao gồm mọi đồng hạng tại ranh giới.

**Đáp án:** Trả `[120/A,110/B,110/C]`, vì điểm ranh giới thứ hai là 110. Nếu chỉ trả đúng N dòng thì chọn `[120/A,110/B]` dựa trên tie-break.

### Bài 15. Vì sao không nên dùng PriorityQueue.iterator để xuất kết quả?

**Đáp án:** `PriorityQueue` chỉ bảo đảm phần tử `peek` là đầu theo comparator; iterator không được bảo đảm duyệt toàn bộ theo thứ tự xếp hạng. Phải tạo list và gọi `sort(BEST_FIRST)` trong finisher.

### Bài 16. Parallel collector có dùng một heap static được không?

**Đáp án:** Không. `PriorityQueue` không thread-safe; dùng chung heap giữa các thread có thể gây race và làm sai top N. `Collector.of` phải có supplier tạo container mới, accumulator thêm vào container của nhánh, combiner ghép các phần, và không công bố `CONCURRENT` sai.

### Bài 17. Kiểm tra top N theo nhóm

**Đề:** Bộ test chỉ kiểm tra `result.get("BOOK").size() <= 2`. Có đủ để khẳng định đúng top 2 không?

**Đáp án:** Không. List có thể chứa hai đơn giá trị thấp hoặc sai nhóm nhưng vẫn đủ điều kiện kích thước. Cần kiểm tra danh mục, trạng thái paid, thứ tự comparator và không bỏ qua ứng viên tốt hơn; so với dữ liệu tính tay hoặc oracle `sorted().limit()`.

### Bài 18. Tình huống dữ liệu bất biến

**Đề:** Một entity trong heap bị sửa `totalCents` giữa chừng. Vì sao kết quả không đáng tin cậy?

**Đáp án:** Thứ tự ưu tiên mà heap dùng để tổ chức dữ liệu thay đổi mà cấu trúc heap không tự cập nhật vị trí theo điểm mới; comparator không còn ổn định trong thời gian xử lý. Hãy dùng snapshot/DTO bất biến hoặc kiểm soát cập nhật nguồn trước khi xếp hạng.

---

## 22. Checklist triển khai top N trong dự án thực

Trước khi công bố một API top N, hãy trả lời:

1. **Top N toàn cục hay top N theo nhóm?** Xác định phạm vi giới hạn rõ ràng.
2. **Đơn vị bản ghi là gì?** Một giao dịch, một người dùng, một phiên bản sản phẩm hay một nhóm tổng hợp?
3. **Điều kiện tham gia?** Trạng thái thanh toán, ngày hiệu lực, quyền truy cập, lọc dữ liệu lỗi.
4. **Comparator có đủ tie-break?** Xác định thứ tự khi hai dòng có cùng tiêu chí chính; tránh tràn và trạng thái mutable.
5. **Chính sách đồng hạng?** Đúng tối đa N hay có thể lớn hơn N vì cùng điểm ranh giới?
6. **N=0, N âm, N vượt kích thước?** Thông báo và kết quả có được định nghĩa không?
7. **Nhóm rỗng có cần xuất hiện?** `groupingBy` không tự tạo khóa không có trong nguồn.
8. **Null/ID trùng được xử lý ở đâu?** Không để ngoại lệ bất ngờ hoặc mất bản ghi không có chính sách.
9. **Nguồn có encounter order không?** Có cần giữ thứ tự gốc khi comparator đồng hạng không?
10. **Cần giữ snapshot?** Dữ liệu có thể bị sửa trong lúc thu thập hoặc sau khi trả kết quả?
11. **Quy mô m, g, N là bao nhiêu?** Chọn sort toàn bộ, heap giới hạn hoặc đẩy xuống tầng truy vấn.
12. **Có oracle?** Ít nhất một bộ dữ liệu nhỏ có kết quả tính tay rõ ràng và các bất biến kiểm tra.
13. **Collector song song có đúng hợp đồng?** Supplier độc lập, combiner không làm mất ứng viên, finisher sắp kết quả.
14. **Benchmark trước khi tối ưu?** Đo thời gian, bộ nhớ, GC và chi phí grouping/sorting với dữ liệu thực.

~~~text
Yêu cầu top N
      |
      v
N là top toàn cục hay theo nhóm?
      |                         |
  TOÀN CỤC                  THEO NHÓM
      |                         |
filter + sorted + limit      groupingBy(
      |                         downstream topN
      |                         )
      +------------+------------+
                   |
                   v
           Dữ liệu quá lớn?
             |          |
             | Không    | Có, N nhỏ
             v          v
          Giữ sort    Cân nhắc heap N
             \          /
              \        /
            Kiểm chứng oracle
                   |
              Thử parallel
                   |
             Benchmark thực tế
                   |
                 Công bố
~~~

---

## Tổng kết

**Top N toàn cục** lấy N phần tử đứng đầu sau khi lọc và xếp hạng trên **toàn bộ nguồn**; **top N theo nhóm** chia dữ liệu theo khóa rồi giới hạn N **riêng từng nhóm**. Cách chuẩn để học và kiểm chứng là `filter().sorted(comparator).limit(n)` cho toàn cục, và `groupingBy(classifier, collectingAndThen(toList(), list -> list.stream().sorted(comparator).limit(n).toList()))` cho từng nhóm.

Với nguồn lớn và N nhỏ, `PriorityQueue` giữ **N ứng viên tốt nhất** có thể tiết kiệm bộ nhớ. Khi viết collector riêng, phải bảo đảm `peek()` là ứng viên **tệ nhất đang được giữ**, combiner ghép đúng ứng viên của hai phân vùng, và finisher sắp lại kết quả để công bố. Những tối ưu đó chỉ có giá trị sau khi đã xác định **khóa xếp hạng, tie-break, đồng hạng, điều kiện lọc và phạm vi nhóm**.

**Ghi nhớ:** Không bao giờ “tối ưu” bằng cách đưa `limit(N)` lên trước `sorted` hoặc `groupingBy` nếu yêu cầu vẫn là top N toàn cục/top N trong từng nhóm. Hãy kiểm tra ý nghĩa kết quả trước, dùng oracle và các ca biên để chứng minh đúng, rồi mới đo lợi ích của heap hoặc Stream song song trong Java Stream API.

