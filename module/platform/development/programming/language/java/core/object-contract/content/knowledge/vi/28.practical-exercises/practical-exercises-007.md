# Thiết kế lớp chứa mảng và kiểm tra sao chép phòng vệ

## 1. Bài toán: lớp chứa mảng có thực sự bất biến?

Ta cần xây dựng một lớp **SensorSnapshot** chứa mã thiết bị **String** và dãy số đo **int[]**. Sau khi tạo snapshot, việc caller thay đổi mảng nguồn hoặc mảng nhận từ getter không được làm thay đổi dữ liệu của snapshot. Đây là bài thực hành tổng hợp về **hợp đồng đối tượng (object contract)**: thiết kế dữ liệu có quyền sở hữu rõ ràng, kiểm thử **equals**, **hashCode**, **toString** và tránh phá vỡ tính ổn định khi đối tượng nằm trong **HashSet/HashMap**.

Kết quả cần đạt:
- Giải thích **aliasing**: nhiều tham chiếu cùng trỏ tới một mảng mutable.
- Sao chép phòng vệ ở cả chiều **constructor nhận vào** và **getter trả ra**.
- So sánh/cấp hash cho mảng theo **giá trị phần tử**, không theo danh tính tham chiếu.
- Xử lý đúng **int[][]** bằng sao chép từng hàng; biết vì sao **Object[]** chứa phần tử mutable khó hơn.
- Dùng phép thử chủ động sửa dữ liệu nguồn và dữ liệu getter để chứng minh các cam kết trên.

Mảng là đối tượng mutable. **private** ngăn code ngoài truy cập trực tiếp tới trường, còn **final** chỉ ngăn gán lại tham chiếu trường; cả hai **không cấm sửa phần tử mảng**. Lớp có thể dùng trường **private final int[]** mà vẫn bị thay đổi từ ngoài.

## 2. Xem lỗi trước khi thiết kế bản đúng

~~~java
// Ví dụ cố ý sai, không phải phần của chương trình chính.
final class UnsafeSnapshot {
    private final int[] values;

    UnsafeSnapshot(int[] input) {
        this.values = input;   // Lỗi: giữ alias của caller.
    }

    int[] values() {
        return values;         // Lỗi: làm lộ mảng nội bộ.
    }
}

// Caller có thể thực hiện:
int[] original = {10, 20};
UnsafeSnapshot unsafe = new UnsafeSnapshot(original);
original[0] = 999;         // Dữ liệu bên trong unsafe cũng đổi.
unsafe.values()[1] = 888;  // Getter tạo đường sửa trực tiếp.
~~~

Hai lỗi độc lập:
1. **Đầu vào:** constructor giữ tham chiếu nguồn; caller vẫn sở hữu mảng và có thể thay đổi nó về sau.
2. **Đầu ra:** getter trả tham chiếu nội bộ; code nhận được getter có thể sửa trạng thái đối tượng.

Mẫu đúng với mảng primitive một chiều:

~~~java
this.values = Objects.requireNonNull(input, "input").clone();

// Getter của lớp:
return values.clone();
~~~

Mỗi lần clone tạo một mảng mới. Vì phần tử **int** là primitive, các giá trị được sao chép độc lập; không còn phần tử tham chiếu tới đối tượng mutable cần xử lý tiếp. **Arrays.copyOf** và **System.arraycopy** cũng là lựa chọn hợp lệ khi dùng đúng độ dài/kiểu, nhưng không tự deep copy các phần tử là object.

Hợp đồng của **SensorSnapshot** được xác định rõ: **sensorId** không null/không blank; **readings** không null nhưng có thể rỗng; thứ tự số đo có ý nghĩa; tất cả thao tác đọc theo giá trị phải nhìn thấy cùng dữ liệu từ lúc tạo; caller được tự do sửa các bản sao getter trả về.

## 3. Chương trình Java 17+ hoàn chỉnh

Tạo tệp đúng tên **DefensiveCopyDemo.java**. Hai lớp lồng **SensorSnapshot** và **MatrixSnapshot** mô tả hai mức sao chép. Hàm **check** ném **AssertionError** nếu hợp đồng không đúng, không phụ thuộc việc có bật **-ea** hay không.

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class DefensiveCopyDemo {
    static final class SensorSnapshot {
        private final String sensorId;
        private final int[] readings;

        SensorSnapshot(String sensorId, int[] readings) {
            this.sensorId = Objects.requireNonNull(sensorId, "sensorId");
            if (sensorId.isBlank()) {
                throw new IllegalArgumentException("sensorId must not be blank");
            }
            this.readings = Objects.requireNonNull(readings, "readings").clone();
        }

        String sensorId() {
            return sensorId;
        }

        int size() {
            return readings.length;
        }

        int readingAt(int index) {
            return readings[index];
        }

        int[] readings() {
            return readings.clone();
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof SensorSnapshot that)) {
                return false;
            }
            return sensorId.equals(that.sensorId)
                    && Arrays.equals(readings, that.readings);
        }

        @Override
        public int hashCode() {
            return 31 * sensorId.hashCode() + Arrays.hashCode(readings);
        }

        @Override
        public String toString() {
            return "SensorSnapshot{sensorId='" + sensorId
                    + "', readings=" + Arrays.toString(readings) + "}";
        }
    }

    static final class MatrixSnapshot {
        private final int[][] values;

        MatrixSnapshot(int[][] source) {
            values = copyRows(source);
        }

        private static int[][] copyRows(int[][] source) {
            Objects.requireNonNull(source, "source");
            int[][] result = new int[source.length][];
            for (int row = 0; row < source.length; row++) {
                result[row] = Objects.requireNonNull(
                        source[row], "source[" + row + "]").clone();
            }
            return result;
        }

        int get(int row, int column) {
            return values[row][column];
        }

        int[][] toArray() {
            return copyRows(values);
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof MatrixSnapshot that)) {
                return false;
            }
            return Arrays.deepEquals(values, that.values);
        }

        @Override
        public int hashCode() {
            return Arrays.deepHashCode(values);
        }

        @Override
        public String toString() {
            return "MatrixSnapshot" + Arrays.deepToString(values);
        }
    }

    private static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
        System.out.println("PASS: " + label);
    }

    public static void main(String[] args) {
        int[] input = {4, 8, 15};
        SensorSnapshot snapshot = new SensorSnapshot("S-1", input);

        input[0] = 999;
        check(snapshot.readingAt(0) == 4, "constructor copy");

        int[] getterResult = snapshot.readings();
        getterResult[1] = 888;
        check(snapshot.readingAt(1) == 8, "getter copy");

        SensorSnapshot same = new SensorSnapshot(
                "S-1", new int[] {4, 8, 15});
        check(snapshot.equals(same) && same.equals(snapshot),
                "value equality");
        check(snapshot.hashCode() == same.hashCode(),
                "equal objects share hashCode");

        Set<SensorSnapshot> set = new HashSet<>();
        set.add(snapshot);
        int[] anotherGetterResult = snapshot.readings();
        anotherGetterResult[2] = -1;
        check(set.contains(same) && set.contains(snapshot),
                "stable HashSet lookup");

        check(snapshot.toString().contains("[4, 8, 15]"),
                "content-based toString");

        int[][] source = {{1, 2}, {3, 4}};
        MatrixSnapshot matrix = new MatrixSnapshot(source);
        source[0][0] = 77;
        source[1] = new int[] {88, 99};
        check(matrix.get(0, 0) == 1 && matrix.get(1, 0) == 3,
                "deep constructor copy");

        int[][] exported = matrix.toArray();
        exported[0][1] = 77;
        exported[1] = new int[] {0};
        check(matrix.get(0, 1) == 2 && matrix.get(1, 0) == 3,
                "deep getter copy");

        MatrixSnapshot sameMatrix = new MatrixSnapshot(
                new int[][] {{1, 2}, {3, 4}});
        check(matrix.equals(sameMatrix)
                        && matrix.hashCode() == sameMatrix.hashCode(),
                "deep value equality and hashCode");

        System.out.println("All 9 checks passed.");
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~text
javac DefensiveCopyDemo.java
java DefensiveCopyDemo
~~~

Stdout mong đợi:

~~~text
PASS: constructor copy
PASS: getter copy
PASS: value equality
PASS: equal objects share hashCode
PASS: stable HashSet lookup
PASS: content-based toString
PASS: deep constructor copy
PASS: deep getter copy
PASS: deep value equality and hashCode
All 9 checks passed.
~~~

### Vì sao 9 phép kiểm có ý nghĩa?

- **constructor copy:** giá trị **input[0] = 999** chỉ sửa dữ liệu do caller còn giữ; snapshot vẫn có số đo 4.
- **getter copy:** sửa **getterResult[1]** không thay đổi mảng bên trong; đọc lại được 8. Nếu bỏ copy tại getter, phép kiểm sẽ thất bại.
- **value equality:** hai mảng khác tham chiếu nhưng cùng chuỗi **4, 8, 15** phải tạo ra hai snapshot bằng nhau khi **sensorId** cũng giống nhau. **Arrays.equals** so phần tử, còn **==** trên mảng so tham chiếu.
- **equal objects share hashCode:** hợp đồng Java yêu cầu **a.equals(b)** đúng thì **a.hashCode() == b.hashCode()**. Ngược lại không bắt buộc: hash collision được phép.
- **stable HashSet lookup:** sau khi thêm snapshot vào HashSet, sửa đầu vào và mảng lấy từ getter không được làm thay đổi các trường góp phần vào equals/hashCode. Nếu hashCode của đối tượng trong set thay đổi, tra cứu có thể thất bại.
- **content-based toString:** **Arrays.toString(int[])** hiển thị phần tử như **[4, 8, 15]**; **readings.toString()** chỉ hiển thị mô tả danh tính mảng kiểu **[I@...**.
- **deep constructor copy:** sửa **source[0][0]** hoặc thay toàn bộ hàng **source[1]** không ảnh hưởng ma trận đã lưu.
- **deep getter copy:** sửa ô của mảng xuất ra hay gán lại một hàng ở kết quả getter cũng không ảnh hưởng ma trận bên trong.
- **deep value equality and hashCode:** cùng dữ liệu ma trận tạo ra equals đúng và hashCode tương ứng nhờ **Arrays.deepEquals/deepHashCode**.

## 4. Vì sao cần phân biệt shallow copy và deep copy?

**int[]** chỉ có giá trị primitive nên **clone()** đủ để tạo bản sao độc lập. Nhưng **int[][]** thực chất là *mảng các tham chiếu tới những mảng int[]*. Chỉ clone mảng ngoài sẽ giữ nguyên tham chiếu tới các hàng.

~~~java
int[][] original = {{1, 2}, {3, 4}};
int[][] shallow = original.clone();
shallow[0][0] = 99;
// original[0][0] cũng là 99: cùng tham chiếu tới hàng 0.

int[][] copied = new int[original.length][];
for (int row = 0; row < original.length; row++) {
    copied[row] = original[row].clone();
}
copied[1][0] = 77;
// original[1][0] vẫn là 3.
~~~

**MatrixSnapshot.copyRows** kiểm tra mảng ngoài và từng hàng không null, tạo mảng ngoài mới, rồi clone từng hàng. Hợp đồng của ví dụ chấp nhận hàng rỗng và mảng không đều (*jagged array*), từ chối hàng **null**. Vì từng hàng chứa primitive, độ sâu hai cấp này đã tách hết dữ liệu mutable liên quan.

Với **MutablePoint[]** thì khác: clone mảng chỉ sao chép tham chiếu tới từng Point; caller có thể sửa **points[0].x**. Phải chụp lại dữ liệu từng Point trong đối tượng độc lập, đồng thời sao chép khi getter trả ra; có thể thay Point mutable bằng một record/snapshot chứa các primitive bất biến. Nếu Point lại chứa mảng hay object mutable khác, copy constructor của Point phải xử lý đến các trường đó.

~~~java
// Minh họa, chưa phải chương trình độc lập:
// MutablePoint phải khai báo constructor MutablePoint(MutablePoint).
static MutablePoint[] copyPoints(MutablePoint[] source) {
    Objects.requireNonNull(source, "source");
    MutablePoint[] result = new MutablePoint[source.length];
    for (int i = 0; i < source.length; i++) {
        result[i] = new MutablePoint(
                Objects.requireNonNull(source[i], "point"));
    }
    return result;
}
~~~

Không nên gọi một phương thức là “deep copy” khi chưa biết hợp đồng mutable của từng đối tượng con. Một **List.copyOf(...)** hoặc **Collections.unmodifiableList(...)** cũng không tự tạo deep copy cho các phần tử là object mutable.

| Dữ liệu nội bộ | Sao chép phù hợp | Rủi ro nếu làm thiếu |
| --- | --- | --- |
| **int[]** | Clone một lần cho từng biên nhận/trả | Alias mảng nguồn hoặc getter |
| **String[]** | Clone mảng, vì String immutable | Alias mảng khi không clone |
| **int[][]** | Clone mảng ngoài và từng hàng | Alias hàng bên trong |
| **MutablePoint[]** | Clone mảng và tạo bản sao từng Point mutable | Alias tới đối tượng phần tử |
| Record chứa **int[]** | Copy mảng trong constructor và accessor, điều chỉnh equals/hashCode | Record component vẫn có mảng mutable; equality mặc định không so giá trị phần tử |

## 5. Object contract: equals, hashCode, toString và tính bất biến

Hợp đồng **equals** của **SensorSnapshot** dùng **sensorId.equals** và **Arrays.equals(readings, that.readings)**. Nếu đổi thứ tự số đo thì hai snapshot không bằng nhau; đây là quyết định nghiệp vụ đã công bố. Nếu thực sự muốn ngữ nghĩa tập không thứ tự, phải đổi mô hình và hợp đồng, không chỉ thay code so sánh tùy tiện.

**hashCode** dùng chính các thông tin trong equals: **31 * sensorId.hashCode() + Arrays.hashCode(readings)**. Không dùng **readings.hashCode()** vì đó là băm theo danh tính mảng và có thể khác giữa hai mảng cùng giá trị. **MatrixSnapshot** sử dụng cặp tương ứng **Arrays.deepEquals** và **Arrays.deepHashCode**.

**toString** chỉ là biểu diễn dễ đọc và kiểm tra, không phải định dạng lưu trữ ổn định. Với mảng một chiều dùng **Arrays.toString**, với mảng lồng nhau dùng **Arrays.deepToString**. Không tự động đưa dữ liệu nhạy cảm vào log nếu snapshot thực tế chứa thông tin bí mật.

**Object.clone()** không phải giải pháp mặc định để tạo immutable object: clone mảng tạo mảng ngoài mới, nhưng với mảng tham chiếu vẫn dùng chung đối tượng con. Bài thực hành dùng constructor có validate và sao chép rõ ràng để hợp đồng dễ đọc.

**final** trên class ngăn subclass thay đổi hành vi theo hướng phá giả định về tính bất biến. **final** trên trường bảo vệ danh tính tham chiếu bên trong lớp nhưng không tự freeze đối tượng được trỏ tới. Mọi cách để state mutable thoát ra ngoài đều phải được xem xét.

**record** không tự giải quyết vấn đề: record có component là **int[]** vẫn nhận/trả một mảng mutable theo accessor mặc định, và equality/hashCode sinh sẵn cho component mảng không tự chuyển thành so sánh nội dung. Muốn dùng record, phải bảo vệ constructor/accessor và override hợp đồng so sánh phù hợp.

## 6. Kiểm thử phòng vệ thực sự cần làm gì?

Khi kiểm tra lớp chứa mảng, chỉ test **assertEquals** trên dữ liệu ngay sau constructor là chưa đủ. Cần tấn công cả hai phía và cả các phần tử nested:

1. Tạo snapshot từ mảng nguồn, **sửa nguồn sau khi đã tạo**, rồi kiểm tra snapshot giữ giá trị cũ.
2. Gọi getter, sửa mảng trả về, đọc lại snapshot và xác minh dữ liệu không đổi.
3. Gọi getter hai lần, kiểm tra **first != second** khi hợp đồng quy định mỗi lần đều trả bản sao mới, đồng thời nội dung bằng nhau.
4. Tạo hai snapshot từ hai mảng **khác danh tính nhưng cùng nội dung**, kiểm tra equals hai chiều và hashCode bằng nhau.
5. Thêm snapshot vào HashSet, sửa dữ liệu nguồn/getter, kiểm tra còn tìm được theo snapshot tương đương.
6. Với matrix, sửa **source[0][0]**, gán lại **source[1]**, và thực hiện các thao tác tương tự trên mảng lấy từ getter.
7. Thử **null**, mảng rỗng, mảng không đều, hàng null, chỉ số sai theo quy tắc API đã chọn.
8. Nếu dùng phần tử là object mutable, thay đổi *bên trong phần tử* chứ không chỉ gán phần tử mới vào mảng.

Có thể bổ sung các phép thử sau **bên trong main** của chương trình mục 3 (chúng dùng các lớp và biến đã khai báo ở đó):

~~~java
SensorSnapshot empty = new SensorSnapshot("S-0", new int[0]);
check(empty.size() == 0, "empty readings accepted");

int[] first = snapshot.readings();
int[] second = snapshot.readings();
check(first != second && Arrays.equals(first, second),
        "fresh getter array");

int[][] jagged = {{1}, {2, 3, 4}};
MatrixSnapshot jaggedCopy = new MatrixSnapshot(jagged);
jagged[1][0] = 100;
check(jaggedCopy.get(1, 0) == 2, "jagged rows copied");
~~~

Đây là phần mở rộng **không độc lập**; khi thêm ba lệnh **check**, kết quả số phép thử in cuối chương trình phải được cập nhật từ 9 lên 12.

## 7. Thiết kế API có trách nhiệm về sở hữu dữ liệu

Sao chép mảng dài có chi phí thời gian và bộ nhớ **O(n)**; sao chép ma trận có chi phí tỷ lệ tổng số phần tử. Không phải API nào cũng cần trả toàn bộ bản sao ở mỗi lần đọc: có thể cung cấp **size()**, **readingAt(i)** hoặc một phép tính tổng hợp để caller không phải copy mảng lớn. Nếu nhất định cần trao quyền sở hữu mảng mà không sao chép, phải công bố hợp đồng ownership/transfer thật rõ và chấp nhận rằng không còn đảm bảo “snapshot bất biến” theo nghĩa của bài này.

Cũng cần nêu chính xác miền dữ liệu chấp nhận. Bài mẫu chủ ý từ chối **sensorId null/blank**, **readings null**, matrix null hoặc hàng null; cho phép **int[]** rỗng và matrix không đều. Các quy tắc khác có thể hợp lý trong sản phẩm khác nhưng phải được viết thành contract và test tương ứng.

Với dữ liệu của nhiều thread, defensive copy bảo vệ **sự sở hữu sau khi sao chép hoàn tất**; nó không làm cho việc đọc đồng thời một mảng nguồn đang bị thread khác sửa trở thành snapshot nguyên tử. Caller phải bảo đảm nguồn ổn định trong lúc copy hoặc phối hợp đồng bộ phù hợp trước khi bàn giao.

## 8. Bài tập tự thực hiện và câu hỏi

**Bài A — phá ranh giới:** tạm xóa clone ở constructor của **SensorSnapshot**, dự đoán phép kiểm nào thất bại. Khôi phục constructor, rồi xóa clone ở getter và giải thích vì sao phép kiểm khác thất bại. Kết thúc với toàn bộ 9 kiểm thử qua.

**Bài B — shallow matrix:** thay **MatrixSnapshot.copyRows** bằng **return source.clone()** (sau khi validate null). Thử sửa **source[0][0]** và gán lại **source[1]**. Hai thao tác có ảnh hưởng khác nhau lên snapshot như thế nào? Sửa lại clone từng hàng.

**Bài C — thêm trường vào value object:** bổ sung **String batchId**. Chỉnh constructor, equals, hashCode, toString cho nhất quán; chứng minh khác batchId thì không bằng nhau ngay cả khi mảng giống nhau.

**Bài D — đối tượng phần tử mutable:** tự viết **MutablePoint**, tạo **PointSnapshot** nhận **MutablePoint[]**, rồi cố ý sửa Point trong nguồn và trong getter. Chứng minh phải copy từng Point và phải xem xét field mutable bên trong Point.

Câu hỏi tự kiểm tra:
1. Vì sao **private final int[] readings** chưa bảo đảm dữ liệu bất biến?
2. Chỉ clone ở constructor hoặc chỉ clone ở getter thì còn đường alias nào?
3. **Arrays.equals** khác **==** trên mảng ra sao?
4. Vì sao **equals** so nội dung thì **hashCode** cũng phải băm theo nội dung?
5. Vì sao **int[][]** cần copy từng hàng, còn **int[]** chỉ cần clone một lần?
6. Vì sao một mảng **MutablePoint[]** đòi hỏi thêm quyết định về bản sao của phần tử?
7. Những phép kiểm nào bảo vệ việc lưu value object trong **HashSet**?
8. Defensive copy có tự giải quyết vấn đề thread khác đang sửa nguồn ngay lúc sao chép không?

**Ghi nhớ:** Lớp chứa mảng chỉ có hợp đồng snapshot an toàn khi bản thân lớp **sở hữu dữ liệu đã được sao chép**, không để lộ alias mutable, copy đủ sâu với cấu trúc lồng nhau, và giữ **equals/hashCode/toString** phù hợp với nội dung có thể quan sát. Các phép thử phải chủ động sửa nguồn và getter rồi xác nhận snapshot vẫn không đổi.
