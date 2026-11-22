# Chọn so sánh theo thứ tự hay theo tập giá trị trước khi viết mã

## 1. Quyết định ý nghĩa của “bằng nhau” trước khi gọi equals

Hai cấu trúc có cùng các giá trị vẫn có thể **bằng nhau hoặc không**, tùy yêu cầu của bài toán. Với mảng, danh sách và cấu trúc lồng nhau, câu hỏi đầu tiên phải là: **vị trí phần tử có mang ý nghĩa hay không, và số lần xuất hiện của mỗi giá trị có mang ý nghĩa hay không?**

Ví dụ, với hai dãy số:

~~~text
A = [2, 1, 2]
B = [1, 2, 2]
C = [1, 1, 2]
~~~

- Nếu so sánh **theo thứ tự**, A khác B vì phần tử ở vị trí đầu tiên khác nhau.
- Nếu so sánh như **tập giá trị (set)**, A, B và C đều đại diện cho tập `{1, 2}`: thứ tự và số lần xuất hiện không quan trọng.
- Nếu so sánh như **đa tập (multiset/bag)**, A bằng B vì cả hai có một số `1` và hai số `2`; A khác C vì C có hai số `1` và một số `2`.
- Nếu cấu trúc là **ánh xạ (map)**, bình đẳng được xác định theo tập các cặp khóa–giá trị, không theo thứ tự duyệt các mục.

Đó là **bốn chính sách bình đẳng khác nhau**. Không nên chọn `Arrays.equals`, `List.equals`, `Set.equals` hay cách chuyển đổi dữ liệu trước khi đã xác định chính sách. Một đoạn code ngắn vẫn có thể đúng cú pháp nhưng sai yêu cầu nghiệp vụ nếu nó chọn nhầm ý nghĩa của “bằng nhau”.

Trong module hợp đồng đối tượng của Java, quyết định này còn chi phối việc cài đặt **cả `equals(Object)` lẫn `hashCode()`**. Nếu hai đối tượng được xem là bằng nhau theo chính sách đã chọn, mã băm của chúng bắt buộc phải giống nhau.

## 2. Ba chính sách thường gặp đối với dãy giá trị

| Chính sách | Thứ tự quan trọng? | Số lần lặp quan trọng? | A so với B | A so với C |
| --- | --- | --- | --- | --- |
| Dãy có thứ tự (sequence) | Có | Có | Khác | Khác |
| Tập giá trị (set) | Không | Không | Bằng | Bằng |
| Đa tập (multiset/bag) | Không | Có | Bằng | Khác |

### 2.1. So sánh theo thứ tự

Dùng khi các vị trí có ý nghĩa: chuỗi bước xử lý, lịch sử sự kiện, tọa độ, thứ tự ưu tiên, danh sách tham số, một hàng dữ liệu có cột cố định, hoặc đường đi theo các nút.

Hai dãy chỉ bằng nhau khi:

1. Có cùng số phần tử.
2. Mỗi cặp phần tử ở **cùng chỉ số** bằng nhau theo chính sách bình đẳng của kiểu phần tử.

Với mảng `int[]`, `Arrays.equals(left, right)` so sánh lần lượt các giá trị nguyên. Với `List<T>`, `List.equals` so sánh phần tử tại từng vị trí bằng `equals` tương ứng. Chỉ thay đổi vị trí hai phần tử khác nhau cũng có thể làm hai dãy không bằng nhau.

### 2.2. So sánh theo tập giá trị

Dùng khi chỉ cần biết **những giá trị nào xuất hiện**, như tập quyền, tập nhãn không lặp, tập mã tính năng bật, hoặc tập ID đã được chọn. Dãy `[2, 1, 2]` và `[1, 2]` biểu thị cùng tập `{1, 2}`, nếu hợp đồng cho phép bỏ qua bản sao trùng lặp.

Một `Set<E>` theo hợp đồng Java không coi thứ tự duyệt là tiêu chí bình đẳng. Hai set bằng nhau khi có cùng các phần tử theo quan hệ `equals` và có cùng kích thước. **Chuyển một dãy sang `Set` là quyết định loại bỏ thông tin về số lần lặp**: đây là thao tác đúng chỉ khi số lượng bản sao không mang ý nghĩa.

Ví dụ, một danh sách người đăng ký có hai dòng giống nhau đôi khi là lỗi cần phát hiện, hoặc là hai lượt đăng ký riêng biệt. Chuyển thẳng nó sang `Set` có thể âm thầm che giấu khác biệt quan trọng.

### 2.3. So sánh theo đa tập

Dùng khi thứ tự không quan trọng nhưng **tần suất xuất hiện** vẫn quan trọng, như giỏ hàng theo số lượng, danh sách nguyên liệu, phân bố nhãn, hoặc kiểm tra hai bộ dữ liệu có cùng phần tử kèm số lần lặp.

Một cách rõ nghĩa là lập bảng tần suất: với mỗi giá trị, đếm số lần xuất hiện, sau đó so sánh các bảng đếm theo `Map.equals`. Đối với `int[]`, ta có thể dùng `Map<Integer, Integer>` và gọi `merge(value, 1, Integer::sum)`.

Việc sắp xếp hai dãy rồi so sánh theo thứ tự cũng có thể kiểm tra bình đẳng đa tập **khi phép sắp xếp và phép so sánh tuân cùng định nghĩa bình đẳng**. Nhưng sắp xếp trực tiếp sẽ thay đổi dãy đầu vào; nếu cần giữ nguyên dữ liệu, phải tạo bản sao trước. Với kiểu tùy biến, comparator có thể coi hai phần tử là tương đương dù `equals` cho `false`; cần xác định rõ chính sách thay vì mặc nhiên xem sắp xếp là đáp án tổng quát.

## 3. Mảng trong Java: tham chiếu, nội dung nông và nội dung lồng

Các phương thức khác nhau trả lời các câu hỏi khác nhau:

| Cách so sánh | Ý nghĩa |
| --- | --- |
| `arrayA == arrayB` | Hai biến có trỏ đến cùng đối tượng mảng không? |
| `arrayA.equals(arrayB)` | Mảng không ghi đè `Object.equals`: kiểm tra cùng đối tượng mảng |
| `Arrays.equals(int[], int[])` | So sánh lần lượt các phần tử `int` theo chỉ số |
| `Arrays.equals(Object[], Object[])` | So sánh từng phần tử bằng `Objects.equals`; mảng con vẫn được xem như đối tượng tham chiếu |
| `Arrays.deepEquals(Object[], Object[])` | So sánh đệ quy nội dung các mảng lồng, kể cả phần tử là mảng primitive |
| `List.equals` | So sánh danh sách theo thứ tự, gọi bình đẳng của từng phần tử |
| `Set.equals` | So sánh theo tập phần tử; không dùng vị trí duyệt |

Ví dụ, hai biến `int[]` khác nhau chứa cùng `[1, 2]` không bằng nhau bằng `==`, nhưng bằng nhau với `Arrays.equals`. Với `int[][]`, các hàng là những đối tượng `int[]` riêng biệt, nên `Arrays.equals(matrixA, matrixB)` thường cho `false` khi các hàng được tạo riêng; `Arrays.deepEquals(matrixA, matrixB)` mới so nội dung từng hàng.

Với cấu trúc mảng lồng, dùng cặp hàm băm phù hợp: `Arrays.hashCode` cho mảng một chiều so theo thứ tự, `Arrays.deepHashCode` cho mảng lồng được so bằng `Arrays.deepEquals`. Không được dùng `Object.hashCode()` mặc định của mảng cho một lớp đã định nghĩa bình đẳng theo nội dung, vì hai mảng khác tham chiếu nhưng cùng nội dung có thể nhận hash khác nhau.

**Lưu ý:** `Arrays.deepEquals` giải quyết cấu trúc **mảng**, nhưng không tự đổi `List` thành tập không thứ tự, cũng không tự đi sâu vào mọi loại đối tượng tùy biến. Khi phần tử là `List` hoặc `Set`, nó sử dụng cách bình đẳng mà các kiểu phần tử đó định nghĩa. Những cấu trúc mảng tự tham chiếu theo chu trình còn cần thiết kế đặc biệt; đừng coi `deepEquals` là bộ so sánh đồ thị tổng quát có xử lý chu trình.

## 4. Ví dụ Java 17 chạy được: một dữ liệu, nhiều kết quả bình đẳng

Chương trình dưới đây minh họa đồng thời so sánh theo thứ tự, theo tập, theo đa tập và theo cấu trúc mảng lồng. Nó cũng đưa vào `HashSet` hai đối tượng có mảng cùng nội dung để kiểm tra `equals`/`hashCode` của lớp chứa mảng.

Lưu trong tệp **ComparisonPolicyDemo.java**:

~~~java
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class ComparisonPolicyDemo {
    static Set<Integer> valuesAsSet(int[] numbers) {
        Set<Integer> result = new HashSet<>();
        for (int number : numbers) {
            result.add(number);
        }
        return result;
    }

    static Map<Integer, Integer> frequencies(int[] numbers) {
        Map<Integer, Integer> count = new HashMap<>();
        for (int number : numbers) {
            count.merge(number, 1, Integer::sum);
        }
        return count;
    }

    static final class OrderedSequence {
        private final int[] values;

        OrderedSequence(int... values) {
            this.values = values.clone();
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof OrderedSequence that
                            && Arrays.equals(values, that.values));
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(values);
        }
    }

    static final class ValueSet {
        private final Set<Integer> values;

        ValueSet(int... numbers) {
            this.values = Set.copyOf(valuesAsSet(numbers));
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof ValueSet that
                            && values.equals(that.values));
        }

        @Override
        public int hashCode() {
            return values.hashCode();
        }
    }

    public static void main(String[] args) {
        int[] a = {2, 1, 2};
        int[] b = {1, 2, 2};
        int[] c = {1, 1, 2};
        int[] sameAsA = {2, 1, 2};

        System.out.println("same array reference: " + (a == sameAsA));
        System.out.println("ordered A/B: " + Arrays.equals(a, b));
        System.out.println("ordered A/copy: "
                + Arrays.equals(a, sameAsA));
        System.out.println("set A/B: "
                + valuesAsSet(a).equals(valuesAsSet(b)));
        System.out.println("set A/C: "
                + valuesAsSet(a).equals(valuesAsSet(c)));
        System.out.println("multiset A/B: "
                + frequencies(a).equals(frequencies(b)));
        System.out.println("multiset A/C: "
                + frequencies(a).equals(frequencies(c)));

        Set<OrderedSequence> orderedKeys = new HashSet<>();
        orderedKeys.add(new OrderedSequence(a));
        System.out.println("ordered HashSet contains copy: "
                + orderedKeys.contains(new OrderedSequence(sameAsA)));
        System.out.println("ordered HashSet contains B: "
                + orderedKeys.contains(new OrderedSequence(b)));

        Set<ValueSet> setKeys = new HashSet<>();
        setKeys.add(new ValueSet(a));
        System.out.println("set-key HashSet contains B: "
                + setKeys.contains(new ValueSet(b)));
        System.out.println("set-key HashSet contains C: "
                + setKeys.contains(new ValueSet(c)));

        int[][] matrixA = {{1, 2}, {3, 4}};
        int[][] matrixB = {{1, 2}, {3, 4}};
        System.out.println("matrix shallow equality: "
                + Arrays.equals(matrixA, matrixB));
        System.out.println("matrix deep equality: "
                + Arrays.deepEquals(matrixA, matrixB));
        System.out.println("matrix deep hashes agree: "
                + (Arrays.deepHashCode(matrixA)
                        == Arrays.deepHashCode(matrixB)));

        List<Set<Integer>> nestedA =
                List.of(Set.of(1, 2), Set.of(3));
        List<Set<Integer>> nestedB =
                List.of(Set.of(2, 1), Set.of(3));
        List<Set<Integer>> nestedReordered =
                List.of(Set.of(3), Set.of(1, 2));
        System.out.println("nested same structure: "
                + nestedA.equals(nestedB));
        System.out.println("nested outer order: "
                + nestedA.equals(nestedReordered));
    }
}
~~~

Dùng JDK 17 trở lên:

~~~bash
javac ComparisonPolicyDemo.java
java ComparisonPolicyDemo
~~~

Kết quả dự kiến chính xác:

~~~text
same array reference: false
ordered A/B: false
ordered A/copy: true
set A/B: true
set A/C: true
multiset A/B: true
multiset A/C: false
ordered HashSet contains copy: true
ordered HashSet contains B: false
set-key HashSet contains B: true
set-key HashSet contains C: true
matrix shallow equality: false
matrix deep equality: true
matrix deep hashes agree: true
nested same structure: true
nested outer order: false
~~~

Giải thích:

- Hai mảng `a` và `sameAsA` là hai đối tượng khác nhau nhưng các phần tử tại từng vị trí giống nhau, nên `==` trả `false` còn `Arrays.equals` trả `true`.
- `a` và `b` không cùng thứ tự; tuy nhiên, cả hai chứa cùng tập `{1, 2}` và cùng số lần xuất hiện của mỗi giá trị. Vì vậy tập và đa tập đều xem chúng là bằng nhau.
- `c` vẫn có tập giá trị `{1, 2}`, nhưng tần suất khác `a`; phép so sánh đa tập phải trả `false`.
- `OrderedSequence` sao chép mảng trong constructor, so nội dung bằng `Arrays.equals`, đồng thời dùng `Arrays.hashCode`. Hai khóa cùng nội dung được `HashSet` nhận diện là cùng giá trị; dãy khác thứ tự thì khác.
- `ValueSet` chuyển đầu vào thành set bất biến, nên bỏ qua thứ tự và số lần lặp. `equals` và `hashCode` đều dựa trên cùng đối tượng `Set`, giữ đúng hợp đồng bình đẳng.
- Hai ma trận có các hàng `int[]` được tạo riêng: so sánh nông không coi các hàng là cùng tham chiếu; so sánh sâu thấy cùng nội dung và có cùng deep hash.
- Cấu trúc `List<Set<Integer>>` dùng **quy tắc kết hợp**: danh sách ngoài quan tâm vị trí, còn mỗi tập bên trong không quan tâm thứ tự. Do đó hoán đổi thứ tự khai báo phần tử trong set vẫn bằng nhau, nhưng đảo vị trí hai set ở danh sách ngoài thì khác.

Cặp `equals`/`hashCode` của hai lớp wrapper minh họa chính sách bình đẳng được mã hóa ở **cấp kiểu dữ liệu**. Hai wrapper có cùng tập đầu vào có thể bằng nhau theo `ValueSet` dù không bằng nhau theo `OrderedSequence`; đây là quyết định thiết kế có chủ đích, không phải mâu thuẫn.

## 5. Cấu trúc lồng nhau: áp dụng chính sách theo từng tầng

Không có quy tắc rằng tất cả các tầng phải cùng quan tâm thứ tự. Hãy xác định ý nghĩa của **mỗi nút** trong cấu trúc dữ liệu:

| Cấu trúc | Quy tắc ở tầng ngoài | Quy tắc ở tầng trong |
| --- | --- | --- |
| `List<List<String>>` | Danh sách ngoài có thứ tự | Mỗi danh sách trong có thứ tự |
| `List<Set<String>>` | Danh sách ngoài có thứ tự | Tập trong không thứ tự, không lặp |
| `Set<List<String>>` | Tập ngoài không thứ tự | Mỗi danh sách trong có thứ tự |
| `Map<String, List<Integer>>` | Các cặp khóa–giá trị không theo thứ tự duyệt map | Danh sách ở từng khóa có thứ tự |
| `int[][]` với `Arrays.deepEquals` | Các hàng theo chỉ số | Phần tử trong mỗi hàng theo chỉ số |

Ví dụ, một `List<Set<String>>` có thể biểu diễn “các giai đoạn có thứ tự, trong mỗi giai đoạn là một nhóm quyền không thứ tự”. Hoán đổi hai quyền trong cùng giai đoạn không đổi ý nghĩa; đảo vị trí hai giai đoạn có thể đổi ý nghĩa. Còn `Set<List<String>>` có thể biểu diễn “tập các đường đi”, nơi thứ tự bước trong một đường đi phải giữ nguyên, nhưng thứ tự liệt kê các đường đi là tùy ý.

Nếu nghiệp vụ yêu cầu một đa tập **ở tầng bên trong**, `Set` không còn phù hợp vì nó loại bỏ bản sao; có thể dùng `Map<Element, Integer>` biểu diễn tần suất cho từng nhóm. Tương tự, nếu yêu cầu “ma trận có cùng các hàng theo bất kỳ thứ tự nào nhưng giữ thứ tự các cột bên trong từng hàng”, ta phải thiết kế chính sách cho tập/đa tập của **các hàng** trước. Không thể chỉ gọi `Arrays.deepEquals` là đủ, vì hàm này vẫn so từng hàng theo vị trí.

Cẩn thận khi dùng các mảng làm phần tử của `Set` hoặc khóa của `Map`: mảng Java mặc định so bình đẳng theo tham chiếu. Chẳng hạn, hai mảng `int[]` độc lập với cùng `[1, 2]` vẫn được coi là hai phần tử **khác nhau** trong `HashSet<int[]>`. Nếu cần tập của các hàng theo nội dung, hãy dùng kiểu wrapper có `equals`/`hashCode` theo `Arrays.equals`, hoặc chuyển mỗi hàng thành kiểu giá trị phù hợp.

## 6. Giữ đúng hợp đồng equals/hashCode với chính sách đã chọn

### 6.1. Bình đẳng có thứ tự

Với lớp chứa `int[] values` và bình đẳng theo dãy, cách phối hợp nhất quán là:

~~~java
@Override
public boolean equals(Object other) {
    return this == other
            || (other instanceof OrderedSequence that
                    && java.util.Arrays.equals(values, that.values));
}

@Override
public int hashCode() {
    return java.util.Arrays.hashCode(values);
}
~~~

Đây là **đoạn phương thức minh họa trong lớp OrderedSequence đã khai báo ở chương trình chính**, không phải tệp Java độc lập. Thay đổi thứ tự phần tử có thể làm thay đổi cả bình đẳng và mã băm. Một số mảng khác nhau vẫn có thể trùng mã băm; điều đó được phép.

### 6.2. Bình đẳng theo tập

Với lớp chứa `Set<Integer> values`:

~~~java
@Override
public boolean equals(Object other) {
    return this == other
            || (other instanceof ValueSet that
                    && values.equals(that.values));
}

@Override
public int hashCode() {
    return values.hashCode();
}
~~~

Đây là **đoạn minh họa trong ValueSet**, không phải chương trình độc lập. Hợp đồng `Set.hashCode` dựa trên các phần tử nên không phụ thuộc thứ tự duyệt. Bởi vậy hai tập bằng nhau phải có hash bằng nhau dù thứ tự duyệt khác.

### 6.3. Bình đẳng theo đa tập

Nếu lớp lưu `Map<T, Integer>` để đếm số lần mỗi phần tử xuất hiện, thì `equals` có thể so hai bảng đếm và `hashCode` dùng `Map.hashCode` trên cùng bảng đếm. Phải bảo đảm số đếm phản ánh đúng dữ liệu được phép, được cập nhật nhất quán và đủ lớn cho số lần xuất hiện thực tế.

Không nên dùng `Arrays.hashCode` theo thứ tự nếu `equals` của lớp lại xem `[2,1,2]` và `[1,2,2]` bằng nhau theo đa tập: hai dãy bằng nhau về nghiệp vụ nhưng rất có thể khác hash, **vi phạm hợp đồng**. Ngược lại, băm theo tập giá trị trong khi `equals` theo thứ tự có thể tạo nhiều va chạm nhưng chưa chắc vi phạm hợp đồng; đó là lựa chọn phân bố kém và khó thể hiện mục đích thiết kế.

## 7. Bảo vệ dữ liệu trước thay đổi trạng thái

Nếu một lớp xác định bình đẳng theo nội dung mảng, việc giữ tham chiếu trực tiếp từ constructor cho phép mã bên ngoài sửa mảng và thay đổi kết quả `equals`/`hashCode` sau khi đối tượng được đưa vào `HashMap` hoặc `HashSet`. Hậu quả là tra cứu có thể thất bại ngay cả khi phần tử vẫn còn trong collection.

Trong ví dụ, `OrderedSequence` gọi `values.clone()` để lấy bản sao của `int[]`. Vì trường là `private final` và không công khai mảng bên trong, nội dung mảng dùng làm khóa không bị thay đổi bởi việc sửa đầu vào sau khi tạo wrapper.

Với mảng hai chiều, **`matrix.clone()` chỉ sao chép mảng ngoài, không tự sao chép các hàng**. Nếu mỗi hàng `int[]` có thể bị sửa, phải sao chép riêng từng hàng hoặc dùng một kiểu bất biến khác. `List.copyOf` hay `Set.copyOf` cũng chỉ đóng băng cấu trúc tập hợp bên ngoài; các phần tử bên trong có thể tiếp tục thay đổi nếu bản thân chúng mutable.

Đối với `List` dùng làm khóa, hãy cân nhắc bản sao bất biến và bảo đảm tất cả phần tử tham gia bình đẳng có trạng thái ổn định. Với tập `Set`, bảo đảm không thay đổi những thuộc tính của phần tử ảnh hưởng tới `equals`/`hashCode`, vì bản thân collection băm cũng phụ thuộc vào chúng.

## 8. Những sai lầm điển hình

### Sai lầm 1: chuyển sang Set chỉ để tránh quan tâm thứ tự

Nếu hai đơn hàng có dòng sản phẩm trùng lặp, chuyển danh sách dòng thành `Set` có thể loại mất ý nghĩa của **số lần xuất hiện**. Khi thứ tự không quan trọng nhưng số lượng quan trọng, cần so đa tập hoặc gom theo khóa cùng tổng số lượng.

### Sai lầm 2: dùng Arrays.equals trên mảng nhiều chiều rồi nghĩ là đã so sâu

`Arrays.equals(int[][], int[][])` so các hàng như các đối tượng `int[]`, thường dẫn tới `false` khi hàng được cấp phát riêng. Nếu mục đích là từng phần tử số ở đúng tọa độ, dùng `Arrays.deepEquals` và `Arrays.deepHashCode` theo cùng chính sách.

### Sai lầm 3: so hai List bằng cách sắp xếp trực tiếp

Sắp xếp tại chỗ làm thay đổi danh sách đầu vào và có thể phá thứ tự nghiệp vụ. Với danh sách không hỗ trợ sửa, thao tác có thể ném `UnsupportedOperationException`. Hãy chọn đúng kiểu dữ liệu ngay từ đầu, hoặc sắp xếp **bản sao** theo tiêu chí phù hợp nếu chính sách thực sự cần so đa tập.

### Sai lầm 4: dùng Set chứa mảng để đại diện cho tập hàng theo nội dung

`HashSet<int[]>` dùng `equals` và `hashCode` mặc định của mảng, tức là theo danh tính đối tượng. Nó không biến hai mảng có cùng nội dung thành phần tử bằng nhau. Cần wrapper, chuyển đổi cấu trúc, hoặc khóa giá trị có hợp đồng phù hợp.

### Sai lầm 5: triển khai equals và hashCode theo hai chính sách khác nhau

Nếu `equals` không quan tâm thứ tự nhưng `hashCode` lại dùng một cách băm nhạy thứ tự, hai đối tượng bằng nhau có thể nhận mã băm khác nhau. Điều này làm hỏng giả định của `HashMap`/`HashSet` và vi phạm hợp đồng.

### Sai lầm 6: giả định mọi Collection đều so nội dung theo cùng quy tắc

`List` và `Set` có hợp đồng bình đẳng khác nhau. Hai collection cùng hiển thị các giá trị tương tự chưa đủ để khẳng định bằng nhau. Với cấu trúc lồng, phải đọc đúng **kiểu dữ liệu và hợp đồng ở từng tầng**.

## 9. Quy trình chọn chính sách trước khi viết mã

Khi gặp đề bài “so sánh hai mảng, hai danh sách hoặc hai cấu trúc lồng”, hãy xác định:

1. **Đơn vị so sánh:** phần tử nguyên thủy, đối tượng tùy biến, hàng của ma trận hay nhóm lồng nhau?
2. **Thứ tự:** đảo vị trí hai phần tử có làm đổi ý nghĩa không? Nếu có, chọn so sánh theo dãy.
3. **Bản sao trùng lặp:** `[A,A,B]` có bằng `[A,B]` không? Nếu có, có thể chọn tập; nếu không mà thứ tự vẫn không quan trọng, chọn đa tập.
4. **Mỗi tầng lồng:** một danh sách các nhóm có thể cần danh sách ngoài theo thứ tự nhưng nhóm bên trong là tập. Viết rõ chính sách cho từng tầng trước.
5. **Đầu vào `null` và phần tử `null`:** quy định `null` được phép ở đâu, cách hiểu hai giá trị thiếu, và chọn API đáp ứng hợp đồng. Ví dụ, `Set.copyOf` không chấp nhận phần tử `null`.
6. **Khả năng thay đổi:** các trường quyết định bình đẳng có thể đổi khi đối tượng đang là khóa trong collection băm không? Nếu có, thiết kế bản sao/bất biến hoặc quy trình cập nhật phù hợp.
7. **Hợp đồng `hashCode`:** nếu các đối tượng bằng nhau theo chính sách chọn, phương thức băm có luôn cho cùng kết quả không?
8. **Ví dụ phản chứng:** thử cặp chỉ khác thứ tự và cặp chỉ khác số lần lặp. Hai ví dụ nhỏ này thường phơi bày ngay một quy tắc bình đẳng sai.

**Ghi nhớ:** “Cùng phần tử” là phát biểu chưa đủ để cài đặt `equals`. Hãy quyết định rõ **thứ tự có quan trọng không**, **số lần xuất hiện có quan trọng không**, và **mỗi tầng lồng nhau mang ý nghĩa gì**. Sau đó mới chọn `Arrays.equals`, `Arrays.deepEquals`, `List.equals`, `Set.equals` hoặc bảng tần suất, đồng thời thiết kế `hashCode` nhất quán với chính sách đã chọn.