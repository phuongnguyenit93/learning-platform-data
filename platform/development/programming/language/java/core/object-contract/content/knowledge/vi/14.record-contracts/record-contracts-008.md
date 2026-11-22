# Tùy biến accessor, chuẩn hóa hoặc sao chép phòng vệ phải giữ hợp đồng record

## 1. Record là kiểu mang giá trị và tính minh bạch của các component

Trong Java 17+, **record** dùng để biểu diễn một nhóm giá trị cố định, với bộ **record component** khai báo ở header:

~~~java
record ProductKey(String tenantId, String sku) {}
~~~

Từ khai báo này, trình biên dịch cung cấp (nếu ta không tự khai báo thành viên tương ứng):

- Các **trường private final** tương ứng với từng component, ở đây là **tenantId** và **sku**.
- **Canonical constructor** nhận đầy đủ các component theo đúng thứ tự và kiểu.
- **Accessor** công khai **tenantId()**, **sku()**; khác getter JavaBean như **getSku()**.
- **equals(Object)**, **hashCode()**, **toString()** được suy ra từ các **trường component**.
- Record ngầm là **final**; không thể tạo subclass kế thừa record để bổ sung trường trạng thái instance.

Các field là **final**, nhưng đây là **bất biến nông (shallow immutability)**: nếu component giữ tham chiếu tới **List**, **Map**, mảng hoặc object mutable, nội dung của các object đó vẫn có thể thay đổi. Vì thế, record không tự biến toàn bộ đồ thị đối tượng thành bất biến sâu.

Record hướng tới tính **minh bạch về trạng thái**: accessor cần mô tả nhất quán với trạng thái mà canonical constructor lưu, và equals/hashCode/toString phải phù hợp với giá trị ấy. Java cho phép tùy biến constructor, accessor và equals/hashCode, nhưng trách nhiệm duy trì hợp đồng thuộc về người viết.

## 2. Bất biến sao chép quan trọng nhất của record

Hợp đồng của **java.lang.Record** yêu cầu: với record **R** có component **c1, c2, ..., cn**, nếu tạo một bản sao bằng cách đưa kết quả accessor của r vào canonical constructor:

~~~java
R copy = new R(r.c1(), r.c2(), ..., r.cn());
~~~

thì **r.equals(copy)** phải là **true**.

Đây là **pseudocode khái quát**, không phải một file Java có thể biên dịch vì R và các tên component chỉ là ký hiệu. Với record cụ thể:

~~~java
ProductKey copy = new ProductKey(original.tenantId(), original.sku());
boolean sameValue = original.equals(copy); // phải là true
~~~

Đoạn trên được sử dụng trong ngữ cảnh đã có biến **original** thuộc kiểu **ProductKey**.

Ngoài bất biến riêng của record, mọi override equals/hashCode phải giữ hợp đồng chung của Object:

1. **Phản xạ:** a.equals(a) true.
2. **Đối xứng:** a.equals(b) có cùng kết quả với b.equals(a).
3. **Bắc cầu:** a bằng b, b bằng c thì a bằng c.
4. **Nhất quán:** kết quả ổn định khi các giá trị dùng so sánh không đổi.
5. **Null:** a.equals(null) false.
6. **Hash:** a.equals(b) true thì a.hashCode() == b.hashCode(); hash giống nhau không bắt buộc equals true.

Với các record bình thường có component bất biến và equals/hashCode sinh tự động, các điều kiện trên thường được bảo đảm bởi chính hợp đồng của từng component. Nếu tự override accessor để **biến đổi dữ liệu lúc đọc**, hoặc sao chép một mảng nhưng tiếp tục dùng equals mặc định theo **danh tính tham chiếu**, có thể phá bất biến sao chép mà compiler không báo lỗi.

**Một chi tiết quyết định:** equals/hashCode/toString sinh ngầm từ record dựa trên **giá trị trường component**, **không có nghĩa** chúng gọi accessor tùy biến trước khi so sánh hoặc tính hash. Do đó, sửa riêng accessor không đồng nghĩa với sửa ngữ nghĩa equals.

## 3. Lỗi 1: chuẩn hóa chỉ trong accessor làm bản sao khác giá trị gốc

Giả sử ta muốn mã sản phẩm có chữ hoa và loại bỏ khoảng trắng bên ngoài. Cách dễ mắc lỗi là **giữ chuỗi gốc trong field**, nhưng trả về chuỗi chuẩn hóa trong accessor.

Tạo file **AccessorNormalizationDemo.java**:

~~~java
import java.util.HashSet;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;

public class AccessorNormalizationDemo {
    record BadCode(String code) {
        @Override
        public String code() {
            return code.strip().toUpperCase(Locale.ROOT);
        }
    }

    record GoodCode(String code) {
        GoodCode {
            code = Objects.requireNonNull(code, "code")
                .strip()
                .toUpperCase(Locale.ROOT);

            if (code.isEmpty()) {
                throw new IllegalArgumentException("code is empty");
            }
        }
    }

    public static void main(String[] args) {
        BadCode bad = new BadCode(" ab-7 ");
        BadCode badCopy = new BadCode(bad.code());

        System.out.println("bad accessor: " + bad.code());
        System.out.println("bad copy equals: " + bad.equals(badCopy));

        GoodCode good = new GoodCode(" ab-7 ");
        GoodCode goodCopy = new GoodCode(good.code());
        GoodCode same = new GoodCode("AB-7");

        System.out.println("good accessor: " + good.code());
        System.out.println("good copy equals: " + good.equals(goodCopy));
        System.out.println("normalized equals: " + good.equals(same));
        System.out.println("matching hash: " +
            (good.hashCode() == same.hashCode()));

        Set<GoodCode> codes = new HashSet<>();
        codes.add(good);
        codes.add(same);
        System.out.println("unique codes: " + codes.size());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac AccessorNormalizationDemo.java
java AccessorNormalizationDemo
~~~

Kết quả:

~~~text
bad accessor: AB-7
bad copy equals: false
good accessor: AB-7
good copy equals: true
normalized equals: true
matching hash: true
unique codes: 1
~~~

### Vì sao BadCode sai?

Trường component của **bad** thực chất lưu **" ab-7 "**. Accessor **bad.code()** trả về **"AB-7"** mà không cập nhật trường đã lưu. Khi dùng giá trị accessor để dựng **badCopy**, trường trong bản sao lưu **"AB-7"**. Vì equals sinh ngầm so hai trường String thực tế, **bad.equals(badCopy)** trả false.

Lỗi này tồn tại dù **bad.code()** và **badCopy.code()** cùng trả **"AB-7"**. Người gọi thấy hai giá trị accessor giống nhau nhưng equals nói chúng khác nhau; record không còn minh bạch với hợp đồng sao chép.

### Vì sao GoodCode đúng?

Record **GoodCode** chuẩn hóa **trước khi lưu** trong **compact canonical constructor**:

~~~java
GoodCode {
    code = Objects.requireNonNull(code).strip().toUpperCase(Locale.ROOT);
}
~~~

Trong constructor dạng compact, tham số component **code** có thể được gán lại; sau khi khối chạy xong, trình biên dịch gán giá trị tham số cuối cùng vào field tương ứng. **Không gán trực tiếp this.code** trong thân compact constructor. Accessor mặc định sau đó đọc ra giá trị đã chuẩn hóa thực sự được lưu.

Kết quả: mọi cách viết được nghiệp vụ xem là cùng mã đều tạo record cùng giá trị; bản sao dựng từ accessor cũng cùng giá trị; equals và hashCode sinh tự động tiếp tục nhất quán.

**Lưu ý nghiệp vụ:** Chỉ dùng **toUpperCase(Locale.ROOT)** khi mã được quy định không phân biệt hoa/thường; không tự động áp dụng cho dữ liệu có phân biệt chữ hoa, tên người hay các mã có luật chuẩn hóa khác. Với Unicode phức tạp hoặc nhận diện tài khoản, cần quy định chuẩn hóa chính xác trước khi áp dụng.

## 4. Tùy biến canonical constructor đúng cách

### Compact constructor và explicit canonical constructor

Hai phong cách sau cùng phục vụ việc xác thực/chuẩn hóa đầu vào, nhưng cơ chế gán field khác nhau.

**Compact constructor** là cách ngắn gọn khi cần xử lý từng component:

~~~java
record Port(int number) {
    Port {
        if (number < 1 || number > 65535) {
            throw new IllegalArgumentException("invalid port");
        }
    }
}
~~~

**Explicit canonical constructor** khai báo đủ danh sách tham số và tự gán tất cả field:

~~~java
record Port(int number) {
    public Port(int number) {
        if (number < 1 || number > 65535) {
            throw new IllegalArgumentException("invalid port");
        }
        this.number = number;
    }
}
~~~

Hai khối trên là **hai định nghĩa thay thế cho cùng một record**, không đặt chung trong cùng một file. Ví dụ record ở cấp top-level với phạm vi package-private, constructor compact có thể không ghi modifier; constructor canonical explicit dùng **public** cũng hợp lệ vì tăng khả năng truy cập. Khi record tự nó được khai báo **public**, canonical constructor tường minh cũng phải đủ mức truy cập **public**.

Không được khai báo cả hai canonical constructor cho cùng chữ ký. Constructor khác nếu có phải ủy quyền đến canonical constructor (theo quy tắc constructor của record).

### Chuẩn hóa phải giữ tính ổn định khi dựng lại

Nếu normalizer là hàm **N**, về mặt thiết kế cần giữ:

~~~text
N(N(x)) = N(x)
~~~

Đây là tính **idempotent**: chuẩn hóa một lần hay nhiều lần cho cùng kết quả. Nếu constructor chuẩn hóa lần hai lại biến đổi giá trị một lần nữa, bản sao dựng từ accessor có thể không equals với bản gốc.

Ví dụ: **strip** và **toUpperCase(Locale.ROOT)** cho một mã đơn giản là idempotent. Các thao tác như tự động cộng phiên bản, gắn timestamp hiện tại, thêm tiền tố lặp lại hoặc sinh ID mới ở mỗi lần gọi constructor thì **không** idempotent nếu đưa kết quả accessor vào constructor.

Trong trường hợp constructor có kiểm tra nhiều component, cần kiểm tra cả **tổ hợp component**, không chỉ từng field riêng lẻ.

## 5. Chuẩn hóa nhiều component cùng nhau: giữ bất biến với canonical constructor

Có những giá trị có nhiều cách biểu diễn tương đương, ví dụ khoảng số với hai đầu mút không cần thứ tự nhập. Ta có thể chuẩn hóa **cả cặp** ngay trong constructor.

Tạo file **RangeRecordDemo.java**:

~~~java
public class RangeRecordDemo {
    record IntRange(int start, int end) {
        IntRange {
            if (start > end) {
                int temp = start;
                start = end;
                end = temp;
            }
        }

        public boolean contains(int value) {
            return value >= start && value <= end;
        }
    }

    public static void main(String[] args) {
        IntRange reversed = new IntRange(9, 2);
        IntRange forward = new IntRange(2, 9);

        IntRange copy =
            new IntRange(reversed.start(), reversed.end());

        System.out.println("range: " + reversed);
        System.out.println("equal: " + reversed.equals(forward));
        System.out.println("copy equal: " + reversed.equals(copy));
        System.out.println("contains five: " + reversed.contains(5));
    }
}
~~~

Chạy:

~~~bash
javac RangeRecordDemo.java
java RangeRecordDemo
~~~

Kết quả:

~~~text
range: IntRange[start=2, end=9]
equal: true
copy equal: true
contains five: true
~~~

Hai tham số đổi chỗ nhưng trạng thái record được chuẩn hóa về cùng cặp **(2, 9)**, nên equals/hashCode mặc định đúng với ý nghĩa mới. Nếu chỉ đảo khi accessor được gọi, còn field vẫn lưu **(9, 2)**, bản sao sẽ phá bất biến tương tự **BadCode**.

**Giới hạn:** Quy tắc này chỉ hợp lý khi miền nghiệp vụ coi các khoảng nhập ngược đầu mút là cùng một khoảng. Nếu thứ tự đầu mút mang ý nghĩa (chẳng hạn hướng hành trình), tự đảo là sai nghiệp vụ dù vẫn giữ hợp đồng Java.

## 6. Lỗi 2: sao chép phòng vệ mảng nhưng giữ equals mặc định

Một record có component **byte[]** dễ gây nhầm lẫn:

~~~java
record RawPacket(byte[] payload) {}
~~~

Mảng **byte[]** không override **Object.equals/hashCode** theo nội dung. Vì vậy hai instance RawPacket chứa hai mảng khác nhau nhưng cùng byte sẽ không equals theo record mặc định.

Nếu sửa bằng cách clone mảng trong constructor và clone tiếp trong accessor, tính an toàn khỏi sửa dữ liệu bên ngoài được cải thiện, **nhưng hợp đồng sao chép của record lại có thể bị vi phạm**: bản sao tạo từ accessor có mảng khác danh tính, trong khi equals ngầm vẫn so tham chiếu.

Tạo file **ArrayCopyContractDemo.java**:

~~~java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;

public class ArrayCopyContractDemo {
    record BadPacket(byte[] payload) {
        BadPacket {
            payload = Objects.requireNonNull(payload).clone();
        }

        @Override
        public byte[] payload() {
            return payload.clone();
        }
    }

    record GoodPacket(byte[] payload) {
        GoodPacket {
            payload = Objects.requireNonNull(payload).clone();
        }

        @Override
        public byte[] payload() {
            return payload.clone();
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof GoodPacket other
                && Arrays.equals(payload, other.payload);
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(payload);
        }

        @Override
        public String toString() {
            return "GoodPacket[payload=" +
                Arrays.toString(payload) + "]";
        }
    }

    public static void main(String[] args) {
        BadPacket bad = new BadPacket(new byte[]{1, 2, 3});
        BadPacket badCopy = new BadPacket(bad.payload());

        System.out.println("bad content equal: " +
            Arrays.equals(bad.payload(), badCopy.payload()));
        System.out.println("bad record equal: " + bad.equals(badCopy));

        byte[] source = {1, 2, 3};
        GoodPacket good = new GoodPacket(source);
        GoodPacket copy = new GoodPacket(good.payload());

        System.out.println("good record equal: " + good.equals(copy));
        System.out.println("good hash equal: " +
            (good.hashCode() == copy.hashCode()));

        Set<GoodPacket> unique = new HashSet<>();
        unique.add(good);
        unique.add(copy);
        System.out.println("unique packets: " + unique.size());

        source[0] = 9;
        byte[] returnedCopy = good.payload();
        returnedCopy[1] = 8;
        System.out.println("after external edits: " + good);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ArrayCopyContractDemo.java
java ArrayCopyContractDemo
~~~

Kết quả:

~~~text
bad content equal: true
bad record equal: false
good record equal: true
good hash equal: true
unique packets: 1
after external edits: GoodPacket[payload=[1, 2, 3]]
~~~

### Vì sao GoodPacket đúng?

- **Compact constructor** clone mảng đầu vào: người gọi sửa **source** sau đó không làm thay đổi trạng thái record.
- **Accessor** trả về một mảng clone: người gọi không nhận được tham chiếu tới mảng nội bộ.
- **equals** dùng **Arrays.equals(byte[], byte[])** để so từng byte.
- **hashCode** dùng **Arrays.hashCode(byte[])** để băm cùng nội dung.
- **toString** được tùy biến thành dạng dễ đọc. Nếu để mặc định, biểu diễn mảng có thể giống **[B@...** do mảng dùng toString theo object.
- Bản sao dựng từ accessor có mảng khác tham chiếu nhưng cùng nội dung, nên bất biến **r.equals(new R(r.component()))** được giữ.
- Khi record dùng làm khóa HashMap/HashSet, hash không bị thay đổi bởi hai đường sửa từ bên ngoài đã được chặn.

**Không sửa bằng cách so nội dung trong equals mà giữ hashCode sinh tự động.** Nếu equals dùng Arrays.equals nhưng hashCode của record vẫn lấy từ component mảng theo danh tính, hai record bằng nội dung có thể có mã băm khác nhau. Khi thay đổi tiêu chí equals của record, phải **đổi hashCode tương ứng**.

## 7. Mảng nhiều chiều và tham chiếu mutable lồng nhau

Đối với **int[][]**, clone mảng ngoài thôi **không đủ**: từng hàng **int[]** vẫn có thể bị chia sẻ và thay đổi. Nếu equals dùng **Arrays.deepEquals** thì hashCode cần dùng **Arrays.deepHashCode**, đồng thời cần sao chép từng mảng con khi cam kết bất biến nội dung.

Một hình mẫu áp dụng trong record chứa ma trận:

~~~java
// Các đoạn trích bên trong record có component int[][] matrix.

static int[][] copyMatrix(int[][] src) {
    Objects.requireNonNull(src);
    int[][] result = new int[src.length][];
    for (int i = 0; i < src.length; i++) {
        result[i] = src[i] == null ? null : src[i].clone();
    }
    return result;
}

// Trong compact canonical constructor:
matrix = copyMatrix(matrix);

// Trong accessor public int[][] matrix():
return copyMatrix(matrix);

// Trong equals(Object) sau kiểm tra đúng record type:
return Arrays.deepEquals(matrix, other.matrix);

// Trong hashCode():
return Arrays.deepHashCode(matrix);
~~~

Các đoạn trên chỉ minh họa **những phần khác nhau trong cùng record**, không phải một chương trình Java độc lập; cần import **java.util.Arrays** và **java.util.Objects**. Cặp deepEquals/deepHashCode được chọn khi ý nghĩa giá trị là **các nội dung mảng lồng nhau**. Với **int[]** một chiều dùng Arrays.equals/hashCode tương ứng.

Nếu mảng chứa **object mutable** ở sâu bên trong, chỉ clone mảng chưa đủ. Muốn bất biến sâu phải sao chép hoặc dùng kiểu bất biến cho từng object lá; không được tuyên bố defensive copy hoàn toàn nếu còn giữ tham chiếu mutable từ người gọi.

## 8. List và Map: sao chép phòng vệ vẫn dùng được equals/hashCode mặc định

Một record chứa **List<String>** có thể an toàn và đơn giản hơn mảng: **List.equals** và **List.hashCode** đã định nghĩa theo phần tử, còn **List.copyOf** có thể tạo biểu diễn không sửa đổi được.

Tạo file **ImmutableListRecordDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class ImmutableListRecordDemo {
    record UserRoles(String userId, List<String> roles) {
        UserRoles {
            userId = Objects.requireNonNull(userId, "userId").strip();
            roles = List.copyOf(Objects.requireNonNull(roles, "roles"));

            if (userId.isEmpty()) {
                throw new IllegalArgumentException("userId is empty");
            }
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("reader"));
        UserRoles first = new UserRoles(" u-1 ", source);
        UserRoles copy = new UserRoles(first.userId(), first.roles());

        System.out.println("user: " + first.userId());
        System.out.println("copy equal: " + first.equals(copy));
        System.out.println("hash equal: " +
            (first.hashCode() == copy.hashCode()));

        source.add("admin");
        System.out.println("after editing source: " + first.roles());

        try {
            first.roles().add("owner");
        } catch (UnsupportedOperationException ex) {
            System.out.println("accessor list cannot be modified");
        }

        System.out.println("final roles: " + first.roles());
    }
}
~~~

Chạy:

~~~bash
javac ImmutableListRecordDemo.java
java ImmutableListRecordDemo
~~~

Kết quả:

~~~text
user: u-1
copy equal: true
hash equal: true
after editing source: [reader]
accessor list cannot be modified
final roles: [reader]
~~~

**Vì sao không phải override equals/hashCode?** List.copyOf tạo ra một list không cho phép sửa cấu trúc và không chứa null, với các phần tử String bất biến trong ví dụ. **List.equals** so phần tử theo thứ tự và **List.hashCode** tương thích. Vì vậy equals/hashCode sinh tự động của record là phù hợp.

**Giới hạn của List.copyOf/Map.copyOf:**

- Đây là dạng sao chép **nông**. Nếu phần tử của List là một object mutable, hoặc value của Map có thể thay đổi, bản ghi vẫn có thể quan sát thấy thay đổi trong object lá.
- List.copyOf không cho phép null phần tử; Map.copyOf không cho phép null key/value. Chọn chính sách dữ liệu trước, thay vì âm thầm thay null.
- **List.equals** nhạy với thứ tự và số lần xuất hiện. Nếu nghiệp vụ coi roles là tập không thứ tự, cần dùng giá trị kiểu Set có hợp đồng tương ứng, hoặc chuẩn hóa cấu trúc trước khi lưu.
- Có thể dùng cấu trúc collection bất biến khác với hợp đồng equals/hashCode thích hợp; vẫn phải kiểm tra đúng ngữ nghĩa miền.

## 9. Tùy biến equals/hashCode và giới hạn của record

### Không bỏ một component trong equals rồi quên sửa hashCode

Ví dụ record sau chứa mã khách hàng và phiên bản:

~~~java
record RevisionedKey(String code, int version) {}
~~~

Mặc định, hai instance chỉ equals khi **code** và **version** đều tương đương. Nếu nghiệp vụ chỉ coi **code** là định danh và ta tự override equals chỉ dựa trên code, thì hashCode sinh tự động vốn lấy cả hai component có thể khác nhau giữa hai record được cho là equals.

Cách tốt hơn thường là **thiết kế record khóa riêng** đúng phạm vi, thay vì ghi đè semantics của record đang biểu diễn đầy đủ dữ liệu:

~~~java
record CustomerCode(String code) {}
record CustomerRevision(CustomerCode id, int version) {}
~~~

Mã dùng để gom nhóm theo khách hàng sẽ lấy **CustomerCode**, còn thông tin phiên bản có thể giữ trong CustomerRevision. Nếu thật sự cần override equals, phải override hashCode theo cùng bộ trường và vẫn duy trì bất biến sao chép.

### Các kiểu component có nghĩa equals đặc biệt

- **BigDecimal**: **new BigDecimal("1.0")** không equals **new BigDecimal("1.00")**, dù compareTo trả 0. Nếu nghiệp vụ muốn cùng trị số, hãy chuẩn hóa component trong constructor (ví dụ stripTrailingZeros khi phù hợp), rồi dùng equals/hashCode mặc định nhất quán.
- **double/float**: equals ngầm của record đối với component primitive dùng ngữ nghĩa **Double.compare/Float.compare** tương ứng, chú ý NaN và sự khác nhau giữa **+0.0** với **-0.0**. Không tùy tiện đổi equals sang phép **==** nếu chưa đồng bộ hashCode và yêu cầu miền.
- **Collection**: List so theo thứ tự; Set so theo tập phần tử; Map so theo cặp khóa–giá trị. Chọn component đúng để equals ngầm có ý nghĩa đúng.
- **Array**: equals/hashCode mặc định không so nội dung mảng; phải dùng wrapper giá trị hoặc tự override cặp phương thức.

### toString cũng phải trung thực về giá trị

Record có toString ngầm dựa trên các field component. Nếu accessor có biến đổi nhưng field không đổi, toString ngầm có thể làm lộ sự không khớp giữa “giá trị lưu” và “giá trị người gọi thấy”.

Khi override toString, nên biểu diễn rõ phần giá trị có ý nghĩa, tránh dùng trạng thái bên ngoài biến động; theo hợp đồng java.lang.Record, các record bằng nhau được kỳ vọng có chuỗi biểu diễn bằng nhau (với ngoại lệ hiếm khi component tương đương nhưng chuỗi của component không giống nhau). Không dựa vào cấu trúc chuỗi toString để phân tích ngược dữ liệu: định dạng cụ thể không phải giao thức serialization.

## 10. Các thiết kế sai khác cần tránh

### Getter cắt/ngụy trang dữ liệu nhưng constructor không cắt

Ví dụ accessor **Math.min(x, 100)** trong khi field lưu 200. Bản sao dựng từ accessor có 100, khiến equals false với giá trị gốc. Nếu muốn luôn giới hạn x ≤ 100, hãy thực hiện ngay trong canonical constructor, để field thật sự lưu giá trị chuẩn.

### Chuẩn hóa có tác dụng phụ hoặc không idempotent

Một constructor tự cộng sequence, sinh thời điểm hiện tại hay nối thêm hậu tố theo lần gọi có thể làm bản sao không equals với gốc. Nếu metadata như thời gian tạo cần được bảo toàn, hãy truyền nó vào component tường minh; không âm thầm sinh lại mỗi khi tái tạo bản sao.

### Chỉ bảo vệ đầu vào, quên bảo vệ accessor

~~~java
record UnsafeData(int[] values) {
    UnsafeData {
        values = values.clone();
    }
}
~~~

Record trên chặn việc sửa mảng đầu vào ban đầu, nhưng accessor sinh mặc định **values()** trả chính tham chiếu tới mảng nội bộ; người dùng vẫn sửa được nội dung. Nếu cần bất biến giá trị thực sự, phải quyết định chính sách accessor và equals/hashCode phù hợp.

### Chỉ bảo vệ accessor, quên constructor

Nếu constructor lưu mảng đầu vào nguyên gốc, người gọi vẫn có thể giữ biến chứa mảng và sửa nội dung sau khi record được tạo. Việc accessor clone lúc đọc không giải quyết alias từ constructor.

### Tin rằng final chặn được sửa object lồng bên trong

Record field là final nhưng **List<MutableItem>** và **Map<String, MutableItem>** có thể thay đổi qua object phần tử. Nếu muốn bất biến sâu, phải kiểm soát cả các giá trị phía trong.

### Chỉ kiểm tra equals mà bỏ qua hashCode

HashMap/HashSet đòi equal keys có hash giống nhau. Cặp record bằng nhau qua Arrays.equals nhưng hashCode theo tham chiếu có thể gây kết quả sai và khó tái hiện. Luôn thử với **hai mảng được cấp phát độc lập**.

### Đảo ngược mục đích của accessor

Nếu muốn một biểu diễn tiện hiển thị khác giá trị lưu, thường nên thêm **phương thức có tên rõ nghĩa**, ví dụ **formattedCode()**, **displayName()**, **normalizedForSearch()**, thay vì làm component accessor trả một giá trị mâu thuẫn với field. Phương thức phụ có thể tùy biến cách biểu diễn mà không phá bất biến copy của record.

## 11. Kiểm thử hợp đồng record một cách có hệ thống

Với record **R(c1, c2, ..., cn)**, hãy viết test theo các nhóm sau.

### A. Tính tái tạo từ accessor

Tạo **r** từ đầu vào có khả năng gây chuẩn hóa, rồi tạo bản sao:

~~~java
R copy = new R(r.c1(), r.c2(), ..., r.cn());
~~~

Trong code thật, thay R và tên component bằng record đang kiểm thử. Kiểm tra **r.equals(copy)** true, **r.hashCode() == copy.hashCode()**, và các accessor tương ứng cho giá trị logic nhất quán. Đây là kiểm tra trực tiếp hợp đồng riêng của record.

### B. Tính idempotent của chuẩn hóa

- Dựng record từ các biểu diễn được quy định là tương đương, chẳng hạn **" A1 "** và **"a1"** đối với mã không phân biệt hoa/thường.
- Dựng lại từ accessor; không được xuất hiện thay đổi lần thứ hai.
- Thử đầu vào null, chuỗi rỗng, cặp component sai ràng buộc; kiểm tra thông báo hoặc loại exception hợp lý.
- Không giả định mọi chuẩn hóa là hợp lệ với miền nghiệp vụ.

### C. Sao chép phòng vệ

- Dùng **mảng/List mutable ban đầu** để khởi tạo, rồi sửa nguồn.
- Lấy component qua accessor và thử sửa kết quả.
- Nếu record tuyên bố bất biến, trạng thái observable, equals và hashCode phải ổn định sau các thử nghiệm đó.
- Với mảng nhiều chiều, sửa **phần tử ở từng tầng**; với List/Map chứa object mutable, thử thay đổi state của object lá.
- So bản sao với bản gốc khi chúng có các mảng được clone riêng.

### D. Hợp đồng Object và collection

- Kiểm tra **r.equals(r)**; **r.equals(null)** false; các cặp đảo chiều cho cùng kết quả.
- Với ít nhất ba đối tượng, kiểm tra bắc cầu nếu hai phép equals liên tiếp true.
- Nếu equals true thì hashCode bắt buộc bằng nhau; đừng yêu cầu hash khác nhau cho mọi cặp không bằng.
- Đưa các instance bằng nhau vào **HashSet**; tra khóa HashMap bằng một bản sao dựng từ accessor phải thành công.
- Nếu có override toString, cân nhắc trường hợp hai object equals nhưng toString khác do tham chiếu mutable hoặc trạng thái ngoài.

### E. Tên file, khả năng chạy và API

Với record khai báo **bên trong lớp demo**, đặt tên file theo **public class** bao ngoài. Với record khai báo **public ở top-level**, đặt tên file trùng tên record. Dùng **Java 17+**; compact canonical constructor và record là tính năng chuẩn từ Java 16. Accessor do mình khai báo phải **public**, không có tham số và đúng kiểu component.

## 12. Chọn cách triển khai theo loại component

| Nhu cầu | Cách triển khai phù hợp | Kiểm chứng bắt buộc |
| --- | --- | --- |
| Component là String/primitive/Instant bất biến và ngữ nghĩa equals đã phù hợp | Giữ accessor và equals/hashCode sinh tự động | Copy invariant, các trường hợp null và chuẩn hóa |
| Đầu vào cần strip, đổi hoa/thường, đưa về khoảng chuẩn | **Chuẩn hóa trong canonical constructor** | N(N(x)) = N(x), dựng lại từ accessor equals true |
| Component là List/Map với các phần tử bất biến | **List.copyOf/Map.copyOf** trong constructor, thường giữ equals/hashCode mặc định | Chống alias đầu vào, không có null ngoài chính sách, copy invariant |
| Component là mảng nhưng muốn so **nội dung** | Clone lúc vào/ra và override **cả equals lẫn hashCode** bằng Arrays tương ứng | Copy invariant, hai mảng riêng cùng nội dung, HashSet |
| Component là mảng đa chiều hoặc cấu trúc lồng mutable | Sao chép từng tầng cần thiết; **deepEquals/deepHashCode** khi quy tắc là so sâu | Không còn mutable alias, hợp đồng từng object lá |
| Chỉ cần chuỗi hiển thị/tính toán khác với trường lưu | Thêm **phương thức riêng** thay vì biến đổi component accessor | Accessor vẫn phản ánh được giá trị dùng để dựng lại record |
| Muốn equals chỉ dựa vào một phần thông tin | Ưu tiên **record khóa riêng**, hoặc override nhất quán nếu thật cần | Equals/hashCode đồng bộ, copy invariant không bị hỏng |

**Ghi nhớ:** Record cho phép tùy biến constructor, accessor và equals/hashCode nhưng các phần này tạo thành **một hợp đồng duy nhất**. Trạng thái quan sát qua accessor phải đủ để tái tạo một giá trị equals với bản gốc; chuẩn hóa nên được thực hiện **trước khi lưu**, còn defensive copy phải được thiết kế cùng **ngữ nghĩa equals/hashCode** của component. Với mảng, clone riêng chưa đủ để giữ hợp đồng: cần so/băm theo nội dung nếu accessor trả bản sao. Với collection có equals theo giá trị và phần tử bất biến, copy bất biến thường cho phép giữ nguyên các phương thức do record sinh tự động.

Tham khảo đặc tả: [java.lang.Record, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).
