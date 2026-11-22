# Enhanced `for` để duyệt mảng hoặc `Iterable` trong Java

> **Java core — language-basics / Duyệt và chuyển luồng**  
> **Phiên bản:** JDK 17+, một file Java độc lập, chỉ dùng thư viện chuẩn.  
> **Mục tiêu:** Dùng đúng vòng lặp *enhanced for* (`for-each`) với mảng và `Iterable`; hiểu cách lấy từng phần tử, thứ tự duyệt, tác dụng của biến vòng lặp, những giới hạn khi cần chỉ số hoặc xóa phần tử.

## 1. Cú pháp và ý nghĩa

~~~java
for (ElementType element : source) {
    // Xử lý element.
}
~~~

`source` phải là **mảng** hoặc biểu thức có kiểu triển khai `java.lang.Iterable`. Trong mỗi lượt, Java lấy một phần tử và gán vào biến cục bộ `element`. Vòng lặp dừng sau khi duyệt hết, hoặc bị ngắt sớm bằng `break`, `return` hay ngoại lệ.

~~~java
int[] scores = {3, 5, 8};
int sum = 0;

for (int score : scores) {
    sum += score;
}
System.out.println(sum); // 16
~~~

`for-each` phù hợp khi chỉ cần **giá trị từng phần tử**, không cần tự quản lý chỉ số. Nó không phải cơ chế tự động chạy song song và cũng không trả về một tập kết quả mới; các thao tác trong thân vẫn được thực hiện tuần tự.

Trong Java 17 cũng có thể viết `for (var item : source)` nếu trình biên dịch suy ra được kiểu phần tử. Với bài nhập môn, viết kiểu rõ như `int` hoặc `String` thường dễ đọc hơn.

## 2. Duyệt mảng: từ đầu đến cuối

`for-each` hỗ trợ mảng kiểu nguyên thủy như `int[]`, `double[]` và mảng tham chiếu như `String[]`:

~~~java
String[] names = {"An", "Binh", "Chi"};

for (String name : names) {
    System.out.println(name);
}
// In An, Binh, Chi theo thứ tự chỉ số 0, 1, 2.
~~~

Về hành vi duyệt phần tử, Java xử lý mảng gần tương đương:

~~~java
for (int index = 0; index < names.length; index++) {
    String name = names[index];
    System.out.println(name);
}
~~~

**Khác biệt:** Với `for-each`, chỉ số không có sẵn dưới tên biến riêng. Nếu cần sửa phần tử tại vị trí cụ thể, duyệt ngược, bỏ qua vị trí chẵn/lẻ hoặc biết chính xác index, dùng vòng `for` theo chỉ số.

| Nhu cầu | Cách thường phù hợp |
| --- | --- |
| Đọc mọi phần tử theo thứ tự | `for (T x : array)` |
| Cập nhật phần tử mảng tại từng chỉ số | `for (int i = 0; i < array.length; i++)` |
| Duyệt từ cuối về đầu | `for` theo chỉ số giảm dần |
| Tính tổng, đếm phần tử, tìm max | `for-each` và biến tích lũy |
| Dừng sớm khi gặp giá trị | `break` hoặc `return` |

## 3. Duyệt `Iterable`: Java sử dụng `Iterator`

`Iterable<T>` là giao diện định nghĩa phương thức `iterator()`. Nhiều collection như `List` và `Set` triển khai `Iterable`:

~~~java
java.util.List<String> colors =
        java.util.List.of("red", "green", "blue");

for (String color : colors) {
    System.out.println(color.toUpperCase(java.util.Locale.ROOT));
}
// In RED, GREEN, BLUE.
~~~

Về ý tưởng, Java thực hiện tương đương với việc lấy một `Iterator` rồi lặp:

~~~java
java.util.Iterator<String> it = colors.iterator();

while (it.hasNext()) {
    String color = it.next();
    System.out.println(color.toUpperCase(java.util.Locale.ROOT));
}
~~~

`Iterable` **không đồng nghĩa** `Iterator`: cái đầu cung cấp `iterator()`, cái sau cung cấp `hasNext()` và `next()` để đi qua dữ liệu. Một `Iterator` đơn lẻ không thể tự đặt sau dấu `:` trong enhanced for nếu không có nguồn `Iterable` thích hợp.

**Thứ tự:** Mảng luôn duyệt theo chỉ số tăng. `List` duyệt theo thứ tự phần tử của list. Với các collection khác, thứ tự phụ thuộc vào contract của iterator; **không nên giả định `HashSet` luôn có thứ tự cố định**. Nếu expected stdout cần xác định, chọn mảng, list hoặc nguồn iterable có thứ tự đã định.

`String` không trực tiếp triển khai `Iterable<Character>`; muốn duyệt ký tự của chuỗi, có thể dùng chỉ số với `charAt` hoặc duyệt mảng từ `toCharArray()`. `Map` không trực tiếp là `Iterable`; để duyệt các cặp key/value, dùng `map.entrySet()`.

## 4. Viết `Iterable` đơn giản của riêng mình

Không nhất thiết phải dùng collection có sẵn. Lớp tự định nghĩa có thể triển khai `Iterable<Integer>` và cung cấp một `Iterator<Integer>`:

~~~java
static final class Range implements Iterable<Integer> {
    private final int from, toExclusive;

    Range(int from, int toExclusive) {
        this.from = from;
        this.toExclusive = toExclusive;
    }

    @Override
    public java.util.Iterator<Integer> iterator() {
        return new java.util.Iterator<>() {
            private int nextValue = from;

            @Override
            public boolean hasNext() {
                return nextValue < toExclusive;
            }

            @Override
            public Integer next() {
                if (!hasNext()) {
                    throw new java.util.NoSuchElementException();
                }
                return nextValue++;
            }
        };
    }
}
~~~

Dùng như mảng hoặc list:

~~~java
int total = 0;
for (int value : new Range(2, 5)) {
    total += value;
}
// Duyệt 2, 3, 4; total == 9.
~~~

Đây là minh họa đơn giản với khoảng tăng và `from <= toExclusive`. Mỗi lần gọi `iterator()` tạo một iterator riêng. Đối với dữ liệu thực, iterator cần duy trì đầy đủ quy tắc `hasNext()/next()`, xác định cách báo hết dữ liệu và cân nhắc thay đổi dữ liệu trong lúc duyệt.

## 5. Giá trị biến vòng lặp không phải ô chứa phần tử gốc

Trong enhanced `for`, mỗi lượt biến cục bộ nhận **bản sao giá trị phần tử**. Với `int[]`, gán lại biến không ghi ngược vào mảng:

~~~java
int[] numbers = {2, 4};
for (int number : numbers) {
    number *= 10;
}
// numbers vẫn là [2, 4]; muốn cập nhật, dùng numbers[i] *= 10.
~~~

Với phần tử kiểu tham chiếu, bản sao tham chiếu vẫn trỏ đến **cùng đối tượng**: `StringBuilder.append` có thể sửa trạng thái đối tượng, nhưng `builder = new StringBuilder("X")` chỉ đổi biến cục bộ. Vì vậy hãy phân biệt *thay đổi đối tượng đang có* với *thay thế phần tử nguồn*. Phần chương trình ở mục 8 cho phép quan sát cả hai trường hợp; các bài tiếp theo đào sâu quy tắc sao chép giá trị và thao tác cập nhật.

## 6. `break`, `continue` và thay đổi collection khi duyệt

`continue` bỏ qua phần còn lại của lượt hiện tại và lấy phần tử tiếp theo; `break` thoát toàn bộ vòng enhanced for hiện tại:

~~~java
int[] values = {1, -2, 0, 5, 7};
int counted = 0;

for (int value : values) {
    if (value < 0) {
        continue; // Bỏ số âm.
    }
    if (value == 5) {
        break; // Không xét 5 và 7.
    }
    counted++; // Chỉ tính 1 và 0.
}
// counted == 2.
~~~

**Không nên thêm/xóa phần tử trực tiếp khỏi một `ArrayList` bên trong `for-each`**:

~~~java
// Không nên làm:
// for (String item : list) {
//     if (item.equals("B")) {
//         list.remove(item); // Có thể gây ConcurrentModificationException.
//     }
// }
~~~

Nhiều iterator của collection thông dụng có cơ chế *fail-fast*, có thể ném `ConcurrentModificationException` khi collection bị thay đổi cấu trúc ngoài iterator. Cơ chế này **không phải bảo đảm đồng bộ hoặc cơ chế phát hiện lỗi tuyệt đối**.

Khi cần xóa phần tử trong lúc duyệt một `ArrayList` có thể thay đổi, dùng `Iterator.remove()` sau `next()` nếu iterator hỗ trợ:

~~~java
java.util.List<String> list = new java.util.ArrayList<>(
        java.util.List.of("A", "B", "C", "B"));

java.util.Iterator<String> it = list.iterator();
while (it.hasNext()) {
    if (it.next().equals("B")) {
        it.remove();
    }
}
// list = [A, C].
~~~

Nếu chỉ cần lọc và không phải xử lý thêm trong cùng lượt, `list.removeIf(predicate)` cũng là lựa chọn rõ ràng. Với collection bất biến như `List.of(...)`, không thể xóa/thay phần tử; tạo một danh sách mới nếu cần kết quả biến đổi.

## 7. `null`, nguồn rỗng và bẫy khi chọn cách duyệt

- Mảng rỗng `new int[0]` hoặc `List.of()`: thân không chạy lần nào; các biến tích lũy giữ giá trị ban đầu.
- **Nguồn là null**: enhanced for cần truy cập mảng hoặc gọi `iterator()`, nên gây `NullPointerException`. Guard trước vòng khi dữ liệu có thể null.
- **Phần tử null** trong mảng/list vẫn có thể được duyệt: vòng lặp không tự bỏ qua. Khi gọi phương thức trên phần tử đó, kiểm tra null.
- `Iterable` có thể trả iterator chạy trên dữ liệu đắt đỏ hoặc biến động; không giả định mọi nguồn duyệt đều rẻ hay lặp lại được như một list.
- Nếu cần biết index, có thể duy trì bộ đếm thủ công cho Iterable, nhưng với mảng/list truy cập chỉ số thì `for` có chỉ số thường dễ rõ ràng hơn.

| Tình huống | Kết quả / lựa chọn |
| --- | --- |
| `for (int x : new int[0])` | 0 lượt |
| `for (String s : List.of("A", "B"))` | 2 lượt theo thứ tự A, B |
| `for (int x : (int[]) null)` | `NullPointerException` |
| Thay biến `x` trong `for (int x : arr)` | Không sửa phần tử của mảng |
| Thay đổi cấu trúc `ArrayList` lúc for-each | Tránh; dùng iterator hỗ trợ `remove()` hoặc xử lý sau |

## 8. Chương trình Java 17+ chạy độc lập

Tạo file **EnhancedForDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.NoSuchElementException;
import java.util.StringJoiner;

public final class EnhancedForDemo {
    static final class Range implements Iterable<Integer> {
        private final int from, toExclusive;

        Range(int from, int toExclusive) {
            this.from = from;
            this.toExclusive = toExclusive;
        }

        @Override
        public Iterator<Integer> iterator() {
            return new Iterator<>() {
                private int nextValue = from;

                @Override
                public boolean hasNext() {
                    return nextValue < toExclusive;
                }

                @Override
                public Integer next() {
                    if (!hasNext()) {
                        throw new NoSuchElementException();
                    }
                    return nextValue++;
                }
            };
        }
    }

    public static void main(String[] args) {
        int[] scores = {3, 5, 8};
        int sum = 0;
        for (int score : scores) {
            sum += score;
        }
        System.out.println("arraySum=" + sum);

        int[] numbers = {2, 4};
        for (int number : numbers) {
            number *= 10;
        }
        System.out.println("arrayReassign=" + Arrays.toString(numbers));

        for (int i = 0; i < numbers.length; i++) {
            numbers[i] *= 10;
        }
        System.out.println("arrayIndexed=" + Arrays.toString(numbers));

        List<String> colors = List.of("red", "green", "blue");
        StringJoiner joiner = new StringJoiner("|");
        for (String color : colors) {
            joiner.add(color.toUpperCase(Locale.ROOT));
        }
        System.out.println("iterableColors=" + joiner);

        int rangeSum = 0;
        for (int value : new Range(2, 5)) {
            rangeSum += value;
        }
        System.out.println("customRangeSum=" + rangeSum);

        List<StringBuilder> labels = new ArrayList<>();
        labels.add(new StringBuilder("A"));
        labels.add(new StringBuilder("B"));
        for (StringBuilder label : labels) {
            label.append("!");
        }
        System.out.println("objectMutation=" + labels);

        int[] values = {1, -2, 0, 5, 7};
        int counted = 0;
        for (int value : values) {
            if (value < 0) {
                continue;
            }
            if (value == 5) {
                break;
            }
            counted++;
        }
        System.out.println("skipAndBreak=" + counted);

        List<String> removable = new ArrayList<>(
                List.of("A", "B", "C", "B"));
        Iterator<String> it = removable.iterator();
        while (it.hasNext()) {
            if (it.next().equals("B")) {
                it.remove();
            }
        }
        System.out.println("iteratorRemove=" + removable);

        int emptyVisits = 0;
        for (int value : new int[0]) {
            emptyVisits++;
        }
        System.out.println("emptyVisits=" + emptyVisits);

        int[] missing = null;
        try {
            for (int value : missing) {
                System.out.println(value);
            }
        } catch (NullPointerException ex) {
            System.out.println("nullArray=NullPointerException");
        }
    }
}
~~~

Biên dịch và chạy tại thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 EnhancedForDemo.java
java EnhancedForDemo
~~~

**Expected stdout chính xác:**

~~~text
arraySum=16
arrayReassign=[2, 4]
arrayIndexed=[20, 40]
iterableColors=RED|GREEN|BLUE
customRangeSum=9
objectMutation=[A!, B!]
skipAndBreak=2
iteratorRemove=[A, C]
emptyVisits=0
nullArray=NullPointerException
~~~

Kết quả `arrayReassign` và `arrayIndexed` làm rõ khác biệt giữa thay **biến vòng lặp** với thay **phần tử thật**. `objectMutation` cho thấy thay đổi trạng thái đối tượng được phản ánh trong list. `customRangeSum` minh họa `Iterable` tự tạo, không cần là một `List`.

## 9. Checklist và bài tập

**Bài 1.** Dùng enhanced for tính tổng và số phần tử dương trong `int[] {4, -3, 0, 7}`. Dự đoán tổng và số đếm.

**Bài 2.** Viết enhanced for duyệt `List<String>` và nối các chuỗi bằng dấu phẩy. Nếu danh sách rỗng, kết quả ra sao?

**Bài 3.** Dự đoán mảng sau `for (int value : numbers) { value++; }` rồi sửa bằng vòng lặp có chỉ số để tăng trực tiếp mọi phần tử.

**Bài 4.** Viết lớp triển khai `Iterable<Integer>` trả các số từ 1 đến 4, kết thúc đúng khi `hasNext()` là false.

**Bài 5.** Với `ArrayList<String>`, xóa các phần tử bằng `"B"` an toàn bằng `Iterator.remove()`. Vì sao không nên sửa cấu trúc list ngay trong vòng for-each?

**Bài 6.** Xử lý một mảng nullable: khi null, trả thông báo rõ ràng; khi rỗng, trả tổng 0; khi có dữ liệu, tính tổng bằng enhanced for.

**Checklist:** Nguồn là mảng hoặc `Iterable` chưa? Có phụ thuộc index/thứ tự không? Có thay cấu trúc collection khi đang duyệt không? Có phân biệt nguồn null với nguồn rỗng không? Nếu muốn cập nhật giá trị gốc, đã chọn cách gán đúng phần tử chưa?

### Ghi nhớ

**Enhanced `for (T element : source)`** là cách duyệt ngắn gọn mảng hoặc `Iterable` khi chỉ cần từng phần tử. Với mảng, duyệt từ chỉ số 0 đến cuối; với `Iterable`, thứ tự do iterator quyết định. Biến `element` không phải địa chỉ để gán lại phần tử nguồn; hãy dùng chỉ số/iterator phù hợp khi cần sửa. Kiểm tra nguồn null, tránh thay đổi cấu trúc collection ngoài iterator và chọn `for` có chỉ số khi cần index.
