# Skeletal implementation: triển khai khung kết hợp interface

**Skeletal implementation** (triển khai khung) là một lớp abstract cung cấp phần lớn hành vi dùng chung của một interface, để mỗi lớp triển khai cụ thể chỉ cần viết những phần cốt lõi còn thiếu. Mẫu này kết hợp ưu điểm của interface — mô tả hợp đồng và cho phép một lớp thực hiện nhiều interface — với ưu điểm của abstract class — chia sẻ mã triển khai, thuật toán và trạng thái khi cần.

Ví dụ, interface có thể định nghĩa một dãy số bằng các thao tác cơ bản như lấy kích thước và đọc phần tử. Một lớp khung có thể dùng hai thao tác đó để triển khai sẵn việc duyệt, tìm kiếm, tính tổng và biểu diễn chuỗi. Lớp cụ thể chỉ cần cung cấp cách lưu trữ và truy cập dữ liệu.

## 1. Ba vai trò trong mẫu thiết kế

| Thành phần | Trách nhiệm |
| --- | --- |
| Interface | Công bố hợp đồng: những thao tác mà mọi implementation phải cung cấp |
| Skeletal implementation | Cài đặt các thao tác có thể suy ra từ hợp đồng, gom logic dùng chung và giữ thuật toán nhất quán |
| Concrete implementation | Cung cấp các thao tác nền tảng phụ thuộc vào cách lưu trữ hoặc nguồn dữ liệu cụ thể |

Mối quan hệ thường có dạng:

```text
Client
  |
  v
Interface (contract)
  ^
  |
Abstract/Skeletal implementation
  ^
  |
Concrete implementation
```

Client nên làm việc qua kiểu interface khi có thể. Nhờ vậy, client phụ thuộc vào hợp đồng công khai thay vì phụ thuộc vào một lớp triển khai cụ thể.

Skeletal implementation là một mẫu thiết kế, không phải từ khóa hay cơ chế đặc biệt của Java. Tên lớp thường bắt đầu bằng `Abstract`, chẳng hạn `AbstractList` hoặc `AbstractCollection`.

## 2. Vì sao kết hợp interface với abstract class?

Interface và abstract class giải quyết những nhu cầu liên quan nhưng khác nhau:

- **Interface** xác định API và cho phép một lớp implements nhiều interface. Các implementation có thể hoàn toàn khác nhau về cấu trúc dữ liệu.
- **Abstract class** có thể cung cấp mã chạy thực tế, trường instance, constructor, phương thức `protected` và các helper dùng chung. Một lớp Java chỉ có thể `extends` một lớp trực tiếp.
- **Skeletal implementation** đặt phần hợp đồng trong interface và phần mã dùng chung trong abstract class. Một implementation có thể kế thừa lớp khung, còn client vẫn sử dụng interface.

Nếu chỉ dùng interface, có thể dùng `default` methods để cung cấp hành vi mặc định. Tuy nhiên, default methods không thay thế hoàn toàn skeletal implementation. Một abstract class có thể lưu trạng thái, có constructor, cung cấp helper `protected`, và tổ chức một thuật toán chung thành các bước mà lớp con tùy chỉnh. Ngoài ra, lớp abstract còn có thể hỗ trợ các phiên bản Java cũ hơn khi default methods chưa tồn tại.

Không cần tạo lớp khung nếu interface chỉ có vài thao tác độc lập, không có logic chung đáng kể, hoặc một abstract class sẽ gây trở ngại vì các lớp triển khai đã cần kế thừa một lớp khác. Hãy chọn mẫu này khi nó thực sự giảm mã lặp và giữ hành vi nhất quán.

## 3. Cách thiết kế một skeletal implementation

Một cách làm hiệu quả là:

1. **Xác định hợp đồng tối thiểu.** Interface chỉ yêu cầu những thao tác mà mọi implementation thực sự có thể cung cấp.
2. **Tìm hành vi có thể suy ra.** Nếu một thao tác có thể được xây dựng từ các thao tác nền tảng, cài đặt nó trong lớp khung.
3. **Giữ lại điểm mở rộng.** Các thao tác phụ thuộc vào cấu trúc dữ liệu cụ thể có thể là abstract để lớp con triển khai.
4. **Dùng các phương thức nền tảng nhất quán.** Phương thức khung nên gọi các phương thức interface thay vì giả định lớp con lưu dữ liệu theo một cách cụ thể.
5. **Kiểm tra hợp đồng và trường hợp biên.** Xác định rõ hành vi với dữ liệu rỗng, chỉ số không hợp lệ, phần tử không tồn tại, và ngoại lệ.
6. **Tạo implementation cụ thể nhỏ.** Nếu lớp cụ thể chỉ phải triển khai một vài phương thức nền tảng, lớp khung đang làm đúng vai trò.

Ví dụ, với một dãy số, `size()` và `get(index)` có thể là hai thao tác nền tảng. Từ đó lớp khung có thể cài đặt sẵn `contains(value)`, `sum()`, `iterator()` và `toString()`. Lớp cụ thể chỉ cần định nghĩa cách tính kích thước và đọc phần tử.

## 4. Ví dụ Java chạy được

Ví dụ dưới đây minh họa ba lớp vai trò. `IntSequence` là interface; `AbstractIntSequence` là lớp khung cung cấp hành vi chung; `ArrayIntSequence` là implementation dùng mảng.

Lưu toàn bộ chương trình trong tệp `Main.java`:

```java
import java.util.Iterator;
import java.util.NoSuchElementException;
import java.util.StringJoiner;

interface IntSequence extends Iterable<Integer> {
    int size();
    int get(int index);
    boolean contains(int value);
    int sum();

    default boolean isEmpty() {
        return size() == 0;
    }
}

abstract class AbstractIntSequence implements IntSequence {
    @Override
    public boolean contains(int target) {
        for (int i = 0; i < size(); i++) {
            if (get(i) == target) {
                return true;
            }
        }
        return false;
    }

    @Override
    public int sum() {
        int total = 0;
        for (int value : this) {
            total += value;
        }
        return total;
    }

    @Override
    public Iterator<Integer> iterator() {
        return new Iterator<>() {
            private int index;

            @Override
            public boolean hasNext() {
                return index < size();
            }

            @Override
            public Integer next() {
                if (!hasNext()) {
                    throw new NoSuchElementException();
                }
                return get(index++);
            }
        };
    }

    @Override
    public String toString() {
        StringJoiner result = new StringJoiner(", ", "[", "]");
        for (int value : this) {
            result.add(Integer.toString(value));
        }
        return result.toString();
    }
}

final class ArrayIntSequence extends AbstractIntSequence {
    private final int[] values;

    ArrayIntSequence(int... values) {
        this.values = values.clone();
    }

    @Override
    public int size() {
        return values.length;
    }

    @Override
    public int get(int index) {
        return values[index];
    }
}

public class Main {
    public static void main(String[] args) {
        IntSequence sequence = new ArrayIntSequence(10, 20, 30);

        System.out.println("size=" + sequence.size());
        System.out.println("empty=" + sequence.isEmpty());
        System.out.println("contains20=" + sequence.contains(20));
        System.out.println("sum=" + sequence.sum());
        System.out.println("values=" + sequence);
    }
}
```

Biên dịch và chạy bằng Java 17 trở lên:

```text
javac Main.java
java Main
```

Kết quả stdout chính xác:

```text
size=3
empty=false
contains20=true
sum=60
values=[10, 20, 30]
```

### Đọc ví dụ theo vai trò

- `IntSequence` công bố `size()`, `get()`, `contains()` và `sum()`. Mọi implementation phải đáp ứng các hợp đồng đó. Interface cung cấp thêm `isEmpty()` bằng `default` method.
- `AbstractIntSequence` cài đặt `contains()`, `sum()`, `iterator()` và `toString()`. Các phương thức này chỉ dựa vào hợp đồng `size()` và `get()`, nên không cần biết dữ liệu được lưu trong mảng hay nguồn khác.
- `ArrayIntSequence` chỉ cung cấp cách lấy kích thước và phần tử từ mảng. Nó kế thừa các hành vi còn lại từ lớp khung.
- Biến `sequence` có kiểu khai báo là `IntSequence`. Client có thể thay `ArrayIntSequence` bằng implementation khác mà không cần thay đổi cách gọi các thao tác được khai báo trong interface.

`ArrayIntSequence` sao chép mảng đầu vào để thay đổi mảng bên ngoài sau khi tạo đối tượng không làm thay đổi dữ liệu nội bộ. Ví dụ giữ đơn giản nên không bổ sung API sửa phần tử.

## 5. Template method và điểm mở rộng

Một skeletal implementation thường dùng ý tưởng **Template Method**: lớp khung định nghĩa quy trình chung, trong đó một số bước gọi phương thức do lớp con triển khai. Ví dụ `sum()` duyệt qua `this`; iterator lần lượt gọi `size()` và `get(index)`. Nhờ vậy, thuật toán tính tổng được viết một lần nhưng vẫn làm việc với nhiều cách lưu trữ.

Điểm mở rộng cần được thiết kế cẩn thận:

- Phương thức abstract chỉ nên đại diện cho thao tác mà implementation cụ thể phải quyết định.
- Phương thức khung nên mô tả rõ tiền điều kiện, hậu điều kiện và ngoại lệ; không dựa vào trạng thái riêng mà interface không bảo đảm.
- Khi một phương thức khung gọi phương thức có thể override, cần cân nhắc liệu lớp con có thể phá vỡ bất biến hoặc tạo ra hành vi bất ngờ hay không.
- Không nên làm mọi phương thức thành `final` một cách máy móc. Điều đó có thể ngăn các implementation tối ưu thuật toán hoặc cần điều chỉnh hành vi trong phạm vi hợp đồng.

Trong ví dụ, `contains()` có thể được tối ưu ở một implementation dùng tập hợp hoặc bảng băm, trong khi implementation mảng có thể dùng cách duyệt tuyến tính mặc định. Lớp khung nên cung cấp cách dùng chung hợp lý mà không làm mất khả năng tối ưu khi có lý do rõ ràng.

## 6. Skeletal implementation trong thư viện Java

Java Collections Framework dùng mẫu này rộng rãi:

- `AbstractCollection<E>` cung cấp một phần hành vi chung cho collection và yêu cầu lớp con triển khai các thao tác nền tảng thích hợp.
- `AbstractList<E>` là khung cho các kiểu `List`; một số implementation dựa vào `get(index)` và `size()`, trong khi các implementation khác có thể override thao tác để tối ưu.
- `AbstractSet<E>` và `AbstractMap<K,V>` cũng cung cấp hành vi chung cho các họ kiểu tương ứng.

Khi sử dụng các lớp này, hãy đọc hợp đồng của interface và tài liệu của abstract class cụ thể để biết phương thức nào bắt buộc override, phương thức nào đã được triển khai và thao tác nào có thể ném `UnsupportedOperationException`. Đừng suy luận rằng mọi phương thức được khai báo trong interface đều đã có một implementation hiệu quả hoặc phù hợp cho mọi cấu trúc dữ liệu.

## 7. Default methods so với skeletal implementation

| Tiêu chí | Interface `default` method | Skeletal implementation |
| --- | --- | --- |
| Vị trí mã dùng chung | Ngay trong interface | Trong abstract class |
| Kế thừa nhiều hợp đồng | Có thể implements nhiều interface | Chỉ extends một lớp trực tiếp |
| Trạng thái instance và constructor | Không có constructor instance; không giữ trường instance thông thường | Có thể có constructor và trạng thái |
| Helper `protected` | Không cung cấp theo cơ chế protected của lớp | Có thể cung cấp |
| Mục tiêu chính | Bổ sung hành vi mặc định cho interface | Chia sẻ một bộ triển khai có cấu trúc, có thể gồm cả thuật toán và trạng thái |

Một interface có thể phối hợp với một skeletal implementation: interface giữ hợp đồng và những default method nhỏ, độc lập; abstract class giữ thuật toán lớn hơn hoặc helper cần trạng thái. Tuy nhiên, tránh đặt cùng một hành vi ở cả hai nơi theo cách khiến quy tắc chọn implementation trở nên khó hiểu.

Nếu một lớp kế thừa từ superclass đã có sẵn, nó không thể đồng thời `extends AbstractIntSequence`. Khi đó, có thể cung cấp một implementation bằng composition, dùng các default methods phù hợp, hoặc tách logic thành helper độc lập. Lựa chọn phụ thuộc vào hợp đồng và khả năng tái sử dụng thực tế.

## 8. Lỗi thiết kế thường gặp

- **Đưa quá nhiều thao tác nền tảng vào interface:** implementation mới phải viết nhiều mã lặp, làm hợp đồng khó đáp ứng.
- **Lớp khung giả định cách lưu trữ cụ thể:** ví dụ truy cập một mảng nội bộ không tồn tại trong các implementation khác. Hãy làm việc qua các phương thức hợp đồng.
- **Bỏ qua hợp đồng ngoại lệ:** `get(index)` có thể ném `IndexOutOfBoundsException`; iterator phải ném `NoSuchElementException` khi hết phần tử. Hành vi cần được nhất quán và được ghi rõ.
- **Sử dụng lớp khung chỉ để có một superclass:** nếu không có mã dùng chung hữu ích, lớp abstract bổ sung độ phức tạp mà không đem lại lợi ích.
- **Quên giới hạn kế thừa đơn:** một implementation không thể kế thừa đồng thời hai lớp khung. Đừng biến skeletal implementation thành điều kiện duy nhất để dùng interface.
- **Coi mã mặc định là tối ưu cho mọi trường hợp:** lớp con có thể cần override các phương thức không phù hợp về hiệu năng, miễn là giữ nguyên hợp đồng.

## 9. Checklist khi áp dụng

Trước khi tạo một skeletal implementation, hãy tự hỏi:

1. Interface đã mô tả đúng hợp đồng tối thiểu chưa?
2. Có những hành vi nào có thể suy ra từ một số ít thao tác nền tảng?
3. Lớp khung có tránh phụ thuộc vào chi tiết lưu trữ cụ thể không?
4. Các trường hợp biên và ngoại lệ có được xác định nhất quán không?
5. Có lý do rõ ràng để dùng abstract class thay cho default methods hoặc composition không?
6. Một implementation cụ thể có thể được viết ngắn gọn bằng cách chỉ cung cấp các thao tác nền tảng không?
7. Client có thể tiếp tục lập trình theo kiểu interface thay vì kiểu lớp cụ thể không?

Skeletal implementation phù hợp khi muốn định nghĩa một interface linh hoạt nhưng vẫn cung cấp phần triển khai dùng chung có cấu trúc. Hãy thiết kế hợp đồng trước, xác định các thao tác nền tảng, rồi đặt logic có thể tái sử dụng vào lớp abstract. Kết quả là các implementation cụ thể ngắn hơn, hành vi nhất quán hơn và client ít phụ thuộc vào chi tiết cài đặt hơn.
