# Tiện ích `Objects` không sửa được `equals()` hoặc `Comparator` đã vi phạm hợp đồng

Lớp `java.util.Objects` cung cấp nhiều phương thức tĩnh tiện dụng để so sánh, tính mã băm, kiểm tra `null` và làm việc với comparator. Các tên như `Objects.equals()`, `Objects.deepEquals()`, `Objects.hash()` và `Objects.compare()` dễ khiến người học tưởng rằng thư viện sẽ tự bảo đảm tính đúng đắn của mọi phép bằng nhau hay thứ tự.

**Thực tế:** tiện ích chỉ cung cấp cách gọi thuận tiện, xử lý một số trường hợp đặc biệt như `null` và mảng, hoặc kết hợp giá trị băm. Nó **không thể tự sửa** một `equals(Object)` thiếu đối xứng, một `hashCode()` không nhất quán với `equals()`, hoặc một `Comparator` không có tính bắc cầu.

## 1. Phân biệt rõ vai trò các phương thức

| Tiện ích | Làm được gì? | Không tự làm được gì? |
| --- | --- | --- |
| `Objects.equals(a, b)` | So sánh hai tham chiếu an toàn với `null`; nếu cần, gọi `a.equals(b)` | Không kiểm tra/sửa tính đối xứng, bắc cầu hay ý nghĩa nghiệp vụ của `equals()` |
| `Objects.deepEquals(a, b)` | So sánh sâu nội dung khi **cả hai là mảng**; trường hợp khác dựa vào equality của đối tượng | Không tự sửa `equals()` bị lỗi của phần tử hay các lớp miền |
| `Objects.hashCode(o)` | Trả `0` nếu `o == null`, ngược lại gọi `o.hashCode()` | Không tạo ra hash đúng nếu chính `o.hashCode()` sai |
| `Objects.hash(values...)` | Kết hợp nhiều giá trị theo `Arrays.hashCode(Object[])` | Không tự biết thuộc tính nào được `equals()` dùng để định nghĩa bằng nhau |
| `Objects.compare(a, b, c)` | Trả `0` nếu cùng tham chiếu; còn lại ủy quyền cho `c.compare(a, b)` | Không sửa comparator sai, không tự biến so sánh gần đúng thành thứ tự hợp lệ |

Các phương thức này đều hữu ích khi được áp dụng **trên một hợp đồng đúng**. Việc gọi thư viện chuẩn không khiến dữ liệu đầu vào, phép so sánh tùy chỉnh hoặc các quyết định thiết kế trở nên đúng một cách tự động.

## 2. Hợp đồng `equals()` và `hashCode()` vẫn do lớp của bạn chịu trách nhiệm

### Phép bằng nhau phải là quan hệ tương đương

Với các tham chiếu đối tượng khác `null`, hợp đồng `Object.equals(Object)` yêu cầu:

- **Phản xạ:** `x.equals(x)` là `true`.
- **Đối xứng:** `x.equals(y)` và `y.equals(x)` có cùng kết quả.
- **Bắc cầu:** nếu `x.equals(y)` và `y.equals(z)` thì `x.equals(z)`.
- **Nhất quán:** khi dữ liệu liên quan không đổi, các lần gọi trả kết quả giống nhau.
- **Xử lý null:** `x.equals(null)` là `false`.

Ngoài ra, với bất kỳ `x` và `y` bằng nhau:

~~~text
x.equals(y) == true  =>  x.hashCode() == y.hashCode()
~~~

Chiều ngược lại không bắt buộc: hai đối tượng khác nhau vẫn có thể có cùng mã băm (*collision*).

Một `equals()` không đối xứng có thể trả `true` theo chiều từ A tới B nhưng `false` theo chiều từ B tới A. `Objects.equals(A, B)` **không kiểm tra hai chiều**. Khi cả hai khác `null` và khác tham chiếu, nó sử dụng phép `A.equals(B)`, nên lỗi đối xứng vẫn tồn tại.

### `Objects.equals()` xử lý null, không kiểm định hợp đồng

Có thể hiểu hành vi của `Objects.equals(a, b)` theo đoạn gần tương đương:

~~~java
return a == b || (a != null && a.equals(b));
~~~

Đây là **mảnh mã giải thích cơ chế** bên trong một phương thức trả `boolean`.

- Hai tham chiếu đều `null` → `true`.
- Một bên `null` và bên còn lại không `null` → `false`.
- Hai tham chiếu trỏ cùng object → `true` mà không cần gọi `equals()`.
- Hai object khác tham chiếu → ủy quyền cho `a.equals(b)`.

Điểm tinh tế: trường hợp cùng tham chiếu có thể trả `true` ngay cả khi lớp viết sai `x.equals(x)` thành `false`. Điều này **không** chứng minh lớp đã tuân thủ tính phản xạ. Khi kiểm thử hợp đồng, hãy kiểm tra trực tiếp `x.equals(x)` cùng các trường hợp hai instance riêng biệt, không chỉ gọi `Objects.equals()`.

## 3. `Objects.hash()` không tự chọn đúng các trường cho bạn

Giả sử hệ thống quyết định hai khách hàng bằng nhau khi cùng `customerId`, bất kể `displayName` khác nhau.

**Đúng về định nghĩa bằng nhau:**

~~~java
@Override
public boolean equals(Object obj) {
    if (this == obj) {
        return true;
    }
    if (!(obj instanceof Customer other)) {
        return false;
    }
    return Objects.equals(customerId, other.customerId);
}
~~~

Đây là **mảnh mã trong lớp `Customer`**. `Objects.equals(customerId, other.customerId)` giúp xử lý trường nullable (nếu thiết kế cho phép), nhưng không tự quyết định rằng ID là khóa nghiệp vụ.

**Sai khi tính hash:**

~~~java
@Override
public int hashCode() {
    return Objects.hash(customerId, displayName);
}
~~~

Nếu hai khách hàng cùng ID nhưng tên hiển thị khác, `equals()` trả `true` còn `Objects.hash(customerId, displayName)` có thể trả hai mã khác nhau. Vì vậy lớp đã vi phạm hợp đồng, cho dù `Objects.hash(...)` là API chuẩn được dùng hoàn toàn đúng cú pháp.

**Đúng khi chỉ ID quyết định bằng nhau:**

~~~java
@Override
public int hashCode() {
    return Objects.hashCode(customerId);
}
~~~

Hoặc có thể dùng `Objects.hash(customerId)`; cùng một ID sẽ sinh cùng kết quả trong cả hai trường hợp. Chúng **không nhất thiết trả cùng con số**: `Objects.hashCode(x)` với `x != null` chính là `x.hashCode()`, còn `Objects.hash(x)` băm một mảng đối số có **một phần tử**, nên thông thường có công thức khác. Cần chọn **cùng chiến lược trong mọi instance của cùng lớp**, không so hai phương thức như thể chúng có nghĩa hoàn toàn giống nhau.

`Objects.hashCode(null)` trả `0`, nhưng xử lý `null` an toàn cũng không cứu được trường hợp hai object bằng nhau mà dữ liệu được hash khác nhau.

## 4. `Objects.compare()` không kiểm định Comparator

Một comparator hợp lệ phải tạo thứ tự có các tính chất nhất quán, đặc biệt tính bắc cầu:

- Nếu `compare(a, b) < 0` và `compare(b, c) < 0` thì `compare(a, c) < 0`.
- Nếu `compare(a, b) == 0`, việc so `a` và `b` với mọi giá trị thứ ba phải cho **cùng dấu kết quả**.
- Dấu của `compare(a, b)` đối xứng với dấu của `compare(b, a)`.

Trả về `0` cho hai giá trị chỉ vì “gần nhau trong phạm vi epsilon” là một lỗi thường gặp. Giả sử `a=0`, `b=1`, `c=2` và ngưỡng gần là `1`:

~~~java
Comparator<Integer> near = (a, b) ->
    Math.abs((long) a - b) <= 1 ? 0 : Integer.compare(a, b);
~~~

Đây là một **mảnh mã minh họa comparator sai**, với `import java.util.Comparator;`. Ta có `near.compare(0, 1) == 0`, `near.compare(1, 2) == 0` nhưng `near.compare(0, 2) < 0`. Hai nhóm “bằng nhau theo comparator” không bắc cầu; thứ tự không hợp lệ. Việc dùng `long` trong phép trừ chỉ để tránh tràn số của hiệu `int`, **không sửa lỗi logic**.

Gọi:

~~~java
Objects.compare(0, 1, near);
Objects.compare(1, 2, near);
Objects.compare(0, 2, near);
~~~

vẫn cho ba kết quả tương ứng `0`, `0`, số âm: utility đã chuyển công việc cho comparator có sẵn. Dùng comparator sai trong `List.sort()` có thể dẫn đến kết quả không đáng tin hoặc ngoại lệ ở một số dữ liệu/thuật toán; dùng trong `TreeSet`/`TreeMap` có thể khiến các khóa “trùng nhau” theo comparator được quản lý không nhất quán.

Thêm một chi tiết: `Objects.compare(a, b, c)` trả ngay `0` nếu `a == b`, không gọi `c.compare(a, b)` trong trường hợp đó. Vì vậy kiểm thử bằng **cùng tham chiếu** có thể che khuất lỗi comparator không trả `0` cho chính một đối tượng. Khi kiểm định comparator, phải gọi trực tiếp `compare(...)` trên các cặp và bộ ba đại diện.

### Không viết Comparator bằng phép trừ

~~~java
Comparator<Integer> broken = (a, b) -> a - b;
Comparator<Integer> correct = Integer::compare;
~~~

`broken.compare(Integer.MIN_VALUE, 1)` trả số dương do tràn `int`, trong khi `Integer.compare(Integer.MIN_VALUE, 1)` trả số âm như thứ tự tăng dần mong muốn. Đặt `broken` vào `Objects.compare(...)` **không** làm phép trừ an toàn hơn. Hãy sửa comparator bằng `Integer.compare`, `Comparator.comparingInt(...)` hoặc những phép so sánh kiểu phù hợp.

## 5. Ví dụ Java 17 chạy được: ba loại lỗi và tiện ích tương ứng

Tạo tệp **`ObjectsContractDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ObjectsContractDemo {

    // Sai: equals chỉ xét ID, hashCode xét cả tên.
    static final class BrokenCustomer {
        private final String id;
        private final String displayName;

        BrokenCustomer(String id, String displayName) {
            this.id = Objects.requireNonNull(id);
            this.displayName = Objects.requireNonNull(displayName);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof BrokenCustomer other)) {
                return false;
            }
            return Objects.equals(id, other.id);
        }

        @Override
        public int hashCode() {
            return Objects.hash(id, displayName);
        }
    }

    // Đúng: cả equals và hashCode cùng dựa trên ID bất biến.
    static final class GoodCustomer {
        private final String id;
        private final String displayName;

        GoodCustomer(String id, String displayName) {
            this.id = Objects.requireNonNull(id);
            this.displayName = Objects.requireNonNull(displayName);
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof GoodCustomer other)) {
                return false;
            }
            return Objects.equals(id, other.id);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(id);
        }
    }

    // Sai: cùng ID nhưng chỉ phía allowMatch=true công nhận bên kia.
    static final class OneWay {
        private final String id;
        private final boolean allowMatch;

        OneWay(String id, boolean allowMatch) {
            this.id = Objects.requireNonNull(id);
            this.allowMatch = allowMatch;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) {
                return true;
            }
            if (!(obj instanceof OneWay other)) {
                return false;
            }
            return allowMatch && Objects.equals(id, other.id);
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(id);
        }
    }

    public static void main(String[] args) {
        BrokenCustomer brokenA = new BrokenCustomer("C-1", "A");
        BrokenCustomer brokenB = new BrokenCustomer("C-1", "B");

        System.out.println("broken equals: "
                + Objects.equals(brokenA, brokenB));
        System.out.println("broken same hash: "
                + (brokenA.hashCode() == brokenB.hashCode()));

        GoodCustomer goodA = new GoodCustomer("C-1", "A");
        GoodCustomer goodB = new GoodCustomer("C-1", "B");
        Set<GoodCustomer> unique = new HashSet<>();
        unique.add(goodA);
        unique.add(goodB);

        System.out.println("good equals: "
                + Objects.equals(goodA, goodB));
        System.out.println("good same hash: "
                + (goodA.hashCode() == goodB.hashCode()));
        System.out.println("good set size: " + unique.size());

        OneWay yes = new OneWay("same", true);
        OneWay no = new OneWay("same", false);
        System.out.println("one way forward: " + Objects.equals(yes, no));
        System.out.println("one way backward: " + Objects.equals(no, yes));

        int[] arrayA = {1, 2};
        int[] arrayB = {1, 2};
        System.out.println("array equals: "
                + Objects.equals(arrayA, arrayB));
        System.out.println("array deep equals: "
                + Objects.deepEquals(arrayA, arrayB));
        System.out.println("deep equals broken customers: "
                + Objects.deepEquals(brokenA, brokenB));

        Comparator<Integer> near = (a, b) ->
                Math.abs((long) a - b) <= 1
                ? 0 : Integer.compare(a, b);

        System.out.println("near 0,1: " + Objects.compare(0, 1, near));
        System.out.println("near 1,2: " + Objects.compare(1, 2, near));
        System.out.println("near 0,2: " + Objects.compare(0, 2, near));

        Comparator<Integer> subtraction = (a, b) -> a - b;
        System.out.println("overflow sign broken: "
                + (Objects.compare(Integer.MIN_VALUE, 1, subtraction) > 0));
        System.out.println("overflow sign fixed: "
                + (Objects.compare(Integer.MIN_VALUE, 1, Integer::compare) < 0));

        System.out.println("null equals: " + Objects.equals(null, null));
        System.out.println("null hashCode: " + Objects.hashCode(null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ObjectsContractDemo.java
java ObjectsContractDemo
~~~

**Kết quả:**

~~~text
broken equals: true
broken same hash: false
good equals: true
good same hash: true
good set size: 1
one way forward: true
one way backward: false
array equals: false
array deep equals: true
deep equals broken customers: true
near 0,1: 0
near 1,2: 0
near 0,2: -1
overflow sign broken: true
overflow sign fixed: true
null equals: true
null hashCode: 0
~~~

Giải thích:

1. Hai `BrokenCustomer` có cùng ID nên `Objects.equals(...)` trả `true`. Tuy nhiên, hai tên `"A"` và `"B"` cho hai hash khác nhau bởi công thức `Objects.hash(id, displayName)`; việc dùng utility không cứu được hợp đồng `equals/hashCode`.
2. Hai `GoodCustomer` có cùng ID và hash giống nhau. `HashSet` loại bản thể hiện trùng ID, nên kích thước là `1`.
3. Hai instance `OneWay` cùng ID trả kết quả khác nhau theo chiều gọi. `Objects.equals(...)` bảo toàn lỗi thiếu đối xứng vì ủy quyền cho toán hạng bên trái.
4. Hai `int[]` khác tham chiếu nên `Objects.equals(...)` trả `false`, nhưng `Objects.deepEquals(...)` so được nội dung mảng và trả `true`. Với hai `BrokenCustomer` (không phải mảng), `deepEquals` vẫn trả `true` qua phép `equals` theo ID, **không tự phát hiện hai mã băm khác nhau**.
5. Comparator `near` cho `0` với `0,1` và `1,2` nhưng `-1` với `0,2`; đó là minh chứng thiếu nhất quán cho một quan hệ bằng nhau theo comparator.
6. Phép trừ trên `int` bị tràn khiến dấu so sánh bị đảo; thay bằng `Integer.compare` sửa **comparator**, còn `Objects.compare` đơn thuần chuyển lời gọi.
7. `Objects.equals(null, null)` và `Objects.hashCode(null)` thể hiện lợi ích xử lý null của utility.

Ví dụ cố tình dùng lớp sai để minh họa điều không nên làm; **không dùng `BrokenCustomer` hoặc `OneWay` làm khóa trong hệ thống thật**. Trái lại, `GoodCustomer` có khóa ID bất biến và đồng bộ `equals()/hashCode()`.

## 6. `deepEquals()` “sâu” đến đâu?

`Objects.deepEquals(a, b)` đặc biệt hữu ích khi **hai đối số là mảng**, bao gồm mảng lồng nhau. Ví dụ:

~~~java
Object[] x = {new int[] {1, 2}, new String[] {"A", "B"}};
Object[] y = {new int[] {1, 2}, new String[] {"A", "B"}};

System.out.println(Objects.deepEquals(x, y)); // true
~~~

Đây là **mảnh mã minh họa** với `import java.util.Objects;`. Hàm sẽ xử lý các mảng con theo nội dung thông qua cơ chế so sánh sâu của `Arrays`.

Tuy nhiên, `deepEquals()` **không phải một công cụ tự động phân tích mọi graph đối tượng**:

- Với hai object thông thường không phải mảng, nó vẫn cần `equals()` của object để xác định bằng nhau. Nếu implementation sai, kết quả có thể sai.
- Với `List<int[]>`, gọi `Objects.deepEquals(listA, listB)` trên hai list riêng biệt sẽ sử dụng `List.equals()`; ở tầng phần tử, hai mảng riêng biệt vẫn có identity equality. Utility không tự thay `List.equals()` bằng thuật toán so sâu cho các phần tử mảng.
- Với mảng có tham chiếu vòng (*cyclic arrays*), không nên giả định phương thức so sâu có thể giải quyết đồ thị tùy ý; recursion có thể gây `StackOverflowError`.

Muốn kiểu miền chứa mảng có **value equality**, hãy thiết kế một lớp bọc với `equals()` gọi `Arrays.equals`/`Arrays.deepEquals` phù hợp và `hashCode()` tương ứng (`Arrays.hashCode`/`Arrays.deepHashCode`), kèm sao chép phòng vệ nếu dữ liệu có thể đổi. Utility không thể tự suy ra những quy tắc đó.

## 7. Sửa ở gốc: thiết kế hợp đồng đúng và kiểm thử cụ thể

### Với `equals()`

1. Xác định “hai đối tượng bằng nhau” theo nghiệp vụ: cùng định danh hay cùng các trường giá trị?
2. Cài đặt `public boolean equals(Object)` đúng chữ ký với `@Override`.
3. Thử các cặp và bộ ba đối tượng **khác instance** để kiểm tra phản xạ, đối xứng và bắc cầu; kiểm tra `null` và sai kiểu.
4. Nếu yêu cầu chỉ là “gần nhau trong ngưỡng”, hãy tách thành `isCloseTo(...)` hoặc API tương tự. So khớp gần đúng không bảo đảm tính bắc cầu và thường không thích hợp làm `equals()`.

### Với `hashCode()`

1. Chọn trường/khóa tạo ra **cùng giá trị hash bất cứ khi nào `equals()` là `true`**.
2. Đảm bảo khóa không đổi trong lúc object nằm trong `HashSet`/`HashMap`.
3. Kiểm tra cụ thể hai instance có `equals()==true` và hash bằng nhau. Không yêu cầu mọi object khác nhau có hash khác nhau.
4. Chọn `Objects.hashCode(singleKey)` hoặc `Objects.hash(key1, key2, ...)` khi phù hợp với định nghĩa bằng nhau. API lựa chọn không thay thế việc xác định trường nào hợp lệ.

### Với `Comparator`

1. Dùng `Comparator.comparing(...)`, `comparingInt/Long/Double(...)` hoặc `Integer.compare`/`Long.compare` thay phép trừ thủ công có nguy cơ tràn.
2. Kiểm tra đối xứng dấu, tính bắc cầu và quy tắc `compare(a,b)==0` đối với mọi giá trị thứ ba.
3. Không đưa phép so gần đúng thiếu bắc cầu vào comparator phục vụ sắp xếp; nếu cần tìm “gần trong ngưỡng”, hãy dùng phương thức lọc/so khớp riêng.
4. Xem xét `null`, NaN, dấu âm của zero và thứ tự nhiều tiêu chí. `Objects.compare(a,b,c)` **không tự xử lý một bên null**: nếu `a` khác `b`, comparator được gọi và có thể ném lỗi nếu nó không hỗ trợ `null`.
5. Nếu dùng trong `TreeSet`/`TreeMap`, xác định `compare(a,b)==0` có đúng là “hai khóa trùng nhau” theo nhu cầu hay không. Dùng comparator khác quy tắc bằng nhau của object có thể khiến tập có thứ tự ứng xử khác `HashSet`.

### Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân cần kiểm tra trước | Cách sửa |
| --- | --- | --- |
| `Objects.equals(a,b)` khác `Objects.equals(b,a)` | `a.equals(b)` / `b.equals(a)` thiếu đối xứng | Sửa `equals()` của kiểu miền |
| Hai đối tượng bằng nhau nhưng `HashSet` coi khác | `hashCode()` không nhất quán hoặc dữ liệu khóa đã bị sửa | Đồng bộ khóa dùng trong `equals()/hashCode()` và giữ bất biến khi lưu |
| `Objects.deepEquals(...)` không so theo ý định | Dữ liệu không phải mảng hoặc phần tử có equality khác kỳ vọng | Định nghĩa equality ở đúng tầng dữ liệu |
| `Objects.compare(...)` cho thứ tự lạ | Comparator bị tràn số, không bắc cầu, sai xử lý null/NaN | Sửa comparator, kiểm thử bộ ba và giá trị biên |
| `TreeSet` bỏ các phần tử “khác nhau” | Comparator trả `0` cho các khóa muốn phân biệt | Bổ sung khóa phụ ổn định, đúng nghiệp vụ |

**Ghi nhớ:** `Objects` giúp code **ngắn hơn, dễ đọc hơn và an toàn với `null` ở những chỗ được thiết kế hỗ trợ**. Nó không có khả năng xác định hộ hợp đồng bằng nhau hay thứ tự của kiểu miền. Nếu `equals()`, `hashCode()` hoặc `Comparator` sai, phải **sửa ở nơi định nghĩa quy tắc và kiểm thử hợp đồng**; bọc lời gọi trong `Objects.equals()`, `Objects.hash()` hoặc `Objects.compare()` không khiến quy tắc sai trở thành đúng.