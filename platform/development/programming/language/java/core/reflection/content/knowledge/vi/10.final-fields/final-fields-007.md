# Field `final`: khả năng quan sát, tối ưu JVM và hành vi theo phiên bản Java

## 1. Vấn đề cần hiểu

Khi Java Reflection cho phép truy cập vào `Field` mang modifier `final`, có ba câu hỏi **khác nhau**:

1. **Có được phép ghi không?** Quyền ghi phụ thuộc loại field, lớp khai báo, ranh giới module, quyền truy cập sâu và phiên bản JDK.
2. **Nếu lời ghi qua Reflection thành công, lần đọc tiếp theo sẽ thấy gì?** Kết quả `Field.get(...)`, lệnh đọc trực tiếp trong bytecode, getter đã được JIT tối ưu và mã đã biên dịch ở nơi khác **không nhất thiết có cùng hành vi quan sát** nếu chương trình sửa `final` sau khi công bố object.
3. **Java/JVM có được tối ưu gì khi field là `final`?** Java Memory Model (JMM) đưa ra bảo đảm riêng cho `final` được khởi tạo đúng; trình biên dịch và JVM có thể dựa vào giả định ổn định giá trị, và hằng số compile-time còn có thể bị **inline tại lúc biên dịch**.

Bài này tập trung vào **ảnh hưởng của việc quan sát/chỉnh sửa field `final` bằng Reflection**, tối ưu và sự khác nhau giữa các phiên bản. Mục tiêu không phải xây thủ thuật cưỡng ép thay đổi mọi `final`: những thao tác như vậy làm suy yếu hợp đồng chương trình và đang bị Java siết chặt.

Sau bài học, bạn sẽ phân biệt được modifier metadata với quyền ghi thực sự, mô tả chính xác giới hạn quan sát giá trị, nhận diện tối ưu dựa trên `final`, thực hiện ví dụ Java 17+, và giải thích các thay đổi ở JDK 26–27.

## 2. `final` bảo đảm điều gì, và không bảo đảm điều gì?

### 2.1. Ngữ nghĩa tại ngôn ngữ Java

- **Biến instance `final`** chỉ được gán theo quy tắc của ngôn ngữ trong quá trình khởi tạo; một **blank final** được gán trong constructor hoặc instance initializer hợp lệ.
- **Biến `static final`** thường được gán khi khai báo hoặc trong static initializer; gán lại bằng source Java bình thường là lỗi biên dịch.
- **`final` trên tham chiếu không làm object được trỏ tới thành bất biến sâu (deeply immutable)**. Ví dụ, một field `final List<String> items` không thể đổi sang một danh sách khác bằng phép gán Java hợp lệ, nhưng có thể gọi `items.add(...)` nếu đối tượng danh sách cho phép.
- **`final` không đồng nghĩa `volatile`**, và bản thân `final` không phải cơ chế cập nhật trạng thái chia sẻ giữa các thread sau khi object đã được tạo.

Ví dụ:

```java
import java.util.ArrayList;
import java.util.List;

class Profile {
    final List<String> tags = new ArrayList<>();

    void addTag(String tag) {
        tags.add(tag); // Hợp lệ: thay đổi nội dung List.
    }
}
```

Đoạn trên là **mã minh họa**, không có `main`; vấn đề của bài là tính ổn định **tham chiếu**, không phải tính bất biến của các phần tử.

### 2.2. Bảo đảm nhìn thấy giá trị khi khởi tạo đúng

Java Memory Model có quy tắc riêng cho `final` trong JLS `17.5. Khi constructor hoàn thành, một **freeze action** cho các field `final` được thiết lập. Nếu object được xây dựng đúng, đặc biệt **không để `this` thoát ra ngoài khi constructor còn chạy**, các thread khác có thể nhận được bảo đảm khởi tạo `final` mạnh hơn so với field thông thường ngay cả trong một số tình huống không có đồng bộ hóa bổ sung.

Nhưng cần đọc đúng giới hạn:

- Quy tắc dành cho **các giá trị được gán trong quá trình khởi tạo hợp lệ** và các truy cập phù hợp với mô hình bộ nhớ.
- Nó **không làm cho mọi field khác** tự động thread-safe.
- Nó **không làm cho mọi thay đổi tiếp theo** của dữ liệu tham chiếu được bảo đảm nhìn thấy.
- Việc để `this` thoát khỏi constructor, chẳng hạn đăng ký callback chạy đồng thời và truy cập object chưa khởi tạo xong, có thể phá hỏng giả định xây dựng đúng.

Để truyền trạng thái có thể thay đổi giữa các thread, hãy dùng cơ chế thích hợp như `volatile`, synchronization, lock, atomic classes hoặc thông điệp bất biến được công bố an toàn. Đừng dùng reflective write vào `final` như một cách thay thế.

## 3. Quan sát field bằng Reflection: metadata khác giá trị

Reflection có thể xác định một field là `final` mà không sửa nó:

```java
Field field = SomeType.class.getDeclaredField("value");
boolean declaredFinal = Modifier.isFinal(field.getModifiers());
```

Đây là **đoạn minh họa**, giả sử `SomeType` có field `value`, đã import `java.lang.reflect.Field` và `java.lang.reflect.Modifier`.

Các API có vai trò riêng:

| API | Điều nó trả lời | Không nên suy ra |
| --- | --- | --- |
| `Field.getModifiers()` + `Modifier.isFinal(...)` | Class file khai báo field mang cờ `final` hay không | Không kết luận `Field.set` chắc chắn thành công hoặc thất bại |
| `Field.get(obj)` / `getInt(obj)` | Đọc giá trị runtime qua Reflection theo quyền truy cập | Không phải một phép đọc `volatile` hay bảo đảm đồng nhất mọi getter sau khi chỉnh `final` |
| `Field.set(obj, value)` / `setInt(...)` | Yêu cầu ghi vào field được phản chiếu | Thành công không làm đổi modifier `final` trong metadata hay định nghĩa bytecode |
| `Field.trySetAccessible()` / `setAccessible(true)` | Thử cho phép vượt một số kiểm tra truy cập ngôn ngữ khi hợp lệ | Không xóa ràng buộc đặc biệt của `final`, record, static field hoặc module |
| `Method.invoke(obj)` gọi getter | Quan sát hành vi mã thực thi của getter | Không mặc định phải trả cùng giá trị như lần đọc `Field.get` sau reflective mutation trái mục đích |

Điểm mấu chốt: **quyền đọc, quyền bỏ qua kiểm tra truy cập và quyền ghi là ba vấn đề tách biệt**. Một field có thể được `setAccessible(true)` để đọc mà **vẫn không được phép ghi**.

### 3.1. Những field `final` không thể mở quyền ghi bằng `setAccessible(true)`

Từ Java 17, Javadoc của `Field` quy định các trường hợp `final` **không thể sửa bằng cơ chế Reflection thông thường**, bao gồm:

- `static final` field trong class hoặc interface.
- `final` field khai báo trong **record class**, bao gồm record component.
- `final` field khai báo trong **hidden class**.

Mở quyền truy cập với `setAccessible(true)`, khi được phép, chỉ giúp **đọc** các field đó; gọi `set(...)` vẫn thất bại với `IllegalAccessException`. Dùng `Unsafe` hoặc sửa nội bộ JVM để vượt ràng buộc nằm **ngoài hợp đồng chuẩn** và không phải giải pháp portable.

Ngược lại, trên JDK 17–25, `Field` thường cho phép ghi vào **non-static `final` instance field** của class thông thường không phải record/hidden class, miễn `setAccessible(true)` thành công. **Được phép thực hiện thao tác** không đồng nghĩa với **bảo đảm chương trình quan sát giá trị mới theo cách bạn mong đợi**.

## 4. Ví dụ Java 17+ độc lập: nhận diện và thử quyền ghi

Lưu toàn bộ đoạn sau vào **`FinalFieldObservationDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

public class FinalFieldObservationDemo {
    static final class Box {
        private final int value;

        Box(int value) {
            this.value = value;
        }

        int read() {
            return value;
        }
    }

    static final class Constants {
        static final int ANSWER = 42;
    }

    record Snapshot(int id) {}

    public static void main(String[] args) throws Exception {
        Box box = new Box(10);

        Field boxField = Box.class.getDeclaredField("value");
        Field constantField = Constants.class.getDeclaredField("ANSWER");
        Field recordField = Snapshot.class.getDeclaredField("id");

        boxField.setAccessible(true);
        constantField.setAccessible(true);
        recordField.setAccessible(true);

        System.out.println("box final="
                + Modifier.isFinal(boxField.getModifiers()));
        System.out.println("box initial=" + boxField.getInt(box));
        System.out.println("constant direct=" + Constants.ANSWER);
        System.out.println("record final="
                + Modifier.isFinal(recordField.getModifiers()));

        try {
            constantField.setInt(null, 99);
            System.out.println("static final write=allowed");
        } catch (IllegalAccessException e) {
            System.out.println("static final write=denied");
        }

        try {
            recordField.setInt(new Snapshot(5), 99);
            System.out.println("record final write=allowed");
        } catch (IllegalAccessException e) {
            System.out.println("record final write=denied");
        }

        try {
            boxField.setInt(box, 20);
            System.out.println("ordinary instance final write=accepted");
        } catch (IllegalAccessException e) {
            System.out.println("ordinary instance final write=denied");
        }

        // Cố ý không khẳng định box.read() sau khi thay đổi phải thấy 20.
    }
}
```

Biên dịch và chạy với JDK 17–25 hoặc chạy thử trên JDK 21:

```bash
javac --release 17 FinalFieldObservationDemo.java
java FinalFieldObservationDemo
```

**Stdout quan sát được khi biên dịch bằng `javac --release 17` và chạy trên OpenJDK 21:**

```text
box final=true
box initial=10
constant direct=42
record final=true
static final write=denied
record final write=denied
ordinary instance final write=accepted
```

Chương trình đã được **biên dịch và chạy thực tế trên OpenJDK 21**; stdout phía trên khớp kết quả kiểm tra. Khi chạy bằng JDK 26–27, reflective mutation của `Box.value` có thể phát cảnh báo **trên stderr** theo JEP 500 và tùy chọn JVM. Khi bật chính sách `--illegal-final-field-mutation=deny` mà không cấp quyền tương ứng, hành vi ghi `Box.value` có thể bị từ chối, khiến dòng cuối đổi thành `ordinary instance final write=denied`.

**Giải thích từng nhóm kết quả:**

1. `Modifier.isFinal` xác định đúng cả `Box.value` và `Snapshot.id` là `final`; metadata không tự cấp quyền sửa.
2. `constantField` là `static final` nên `setInt(null, 99)` bị từ chối. `null` ở đây hợp lệ để chỉ target của static field, nhưng không làm field trở nên ghi được.
3. `recordField` biểu diễn record component `id`, là `final` và không thể sửa qua `Field.setInt`.
4. `Box.value` là `final` instance field của class thường. Với JDK 21, khi đã bật `setAccessible(true)`, thao tác `setInt(box, 20)` được chấp nhận.
5. Ví dụ cố ý **không kết luận** rằng sau lời ghi, `box.read()` hay một vòng lặp trên thread khác sẽ luôn thấy `20`. Đó chính là chủ đề về **khả năng quan sát và tối ưu** của bài này.

Nếu target class nằm ở **named module khác** mà package không mở cho module caller, lời `setAccessible(true)` còn có thể thất bại với `InaccessibleObjectException` trước khi chương trình đến bước kiểm tra ghi.

## 5. Vì sao ghi `final` thành công vẫn không bảo đảm lần đọc thấy giá trị mới?

### 5.1. JLS cho phép tối ưu dựa trên `final`

JLS `17.5.3, **Subsequent Modification of `final` Fields**, thảo luận trường hợp hệ thống như deserialization cần sửa `final` sau khi object được dựng. Quy tắc này chỉ có ngữ nghĩa hợp lý trong một mô hình đặc biệt: tạo object, cập nhật field trước khi object được **công bố** cho các phần khác, và không cho mã khác đọc field cho đến khi cập nhật xong.

Đối với tình huống object **đã được sử dụng/đọc/công bố**, chương trình không thể xem reflective mutation như cập nhật trạng thái thường xuyên được bảo đảm. JLS thừa nhận compiler/JVM có thể tối ưu `final` rất mạnh, kể cả các phép biến đổi thứ tự đọc liên quan đến thao tác sửa `final` không nằm trong constructor.

Một mô hình minh họa về hậu quả:

```java
final class Counter {
    final int value;

    Counter(int value) {
        this.value = value;
    }

    int read() {
        return value;
    }
}
```

Đây chỉ là **class minh họa**, không phải chương trình độc lập. Nếu tạo `Counter(1)`, cho code đọc `read()` nhiều lần, sau đó dùng Reflection đổi `value` thành `2`, không có bảo đảm tổng quát rằng:

- Một lần gọi `read()` đã được JIT tối ưu sẽ luôn tải lại field từ bộ nhớ.
- Một thread khác sẽ thấy `2` ngay hoặc tại một thời điểm hữu hạn.
- Mọi phương thức/đường đọc có quan sát giống hệt `Field.getInt(...)`.
- Chạy interpreter và JIT tối ưu sẽ cho kết quả giống nhau.

**Đừng viết unit test khẳng định “sau `Field.set`, getter phải đọc giá trị mới” như một hợp đồng ổn định của Java.** Một lần chạy thấy giá trị mới chỉ chứng minh điều xảy ra trong điều kiện chạy đó.

### 5.2. Ba mức “quan sát” cần tách

| Lớp quan sát | Ví dụ | Kết luận có thể rút ra |
| --- | --- | --- |
| **Metadata** | `Modifier.isFinal(field.getModifiers())` | Field được khai báo `final`, không có nghĩa value không từng bị ghi sau constructor |
| **Lần đọc reflective cụ thể** | `field.getInt(instance)` | Giá trị do truy cập Reflection đó trả về tại thời điểm và execution path cụ thể |
| **Lệnh đọc trong code ứng dụng** | `instance.read()`, code JIT hoặc code biên dịch khác | Có thể chịu constant folding, hoisting, cached reads và ràng buộc JMM; không tự đồng bộ với reflective mutation |

Đặc biệt, khi kiểm thử race condition, thêm logging hoặc Reflection có thể làm thay đổi timing, đường thực thi và mức độ tối ưu. Việc **bật giám sát rồi hết lỗi** không chứng minh lỗi đa luồng ban đầu đã được sửa.

### 5.3. “Freeze” sau reflective write không biến mutation thành thiết kế hợp lệ

JLS mô tả freeze action tại cuối constructor và ngay sau một số reflective modifications hợp lệ của `final`. Tuy nhiên, đây không phải giấy phép dùng `final` như biến mutable. Phạm vi dự kiến là trường hợp rất hẹp như **tái dựng/deserialization**, khi field được đặt giá trị **trước khi object bị đọc/công bố**.

Nếu object đã được chia sẻ, đã bị getter đọc nhiều lần hoặc rơi vào một vòng lặp JIT, không thể viện dẫn freeze action để ép mọi luồng/ngữ cảnh biên dịch thấy phiên bản mới.

## 6. Tối ưu quan trọng: `static final` compile-time constant

Không phải mọi `final` đều là **constant variable** theo JLS. Một field là constant variable khi nó có kiểu primitive hoặc `String`, là `final` và được khởi tạo bằng một **constant expression** theo quy tắc ngôn ngữ.

Ví dụ:

```java
class ConstantsExample {
    static final int MAX = 42;            // Constant variable
    static final String LABEL = "READY";   // Constant variable

    static final Integer BOXED = 42;       // Không phải constant variable
    static final int COMPUTED = Integer.parseInt("42");
                                         // Không phải constant expression
}
```

Đây là **đoạn minh họa**. `MAX` và `LABEL` có thể bị **inline khi compile** tại nơi sử dụng. Nếu một class client được compile với `ConstantsExample.MAX == 42`, bytecode của client có thể chứa hẳn số `42` thay vì đọc field lúc chạy.

Do vậy:

- Ngay cả trong giả thiết dùng cách ngoài chuẩn để làm thay đổi storage của `static final`, những code path đã inline literal có thể **vẫn dùng giá trị cũ**.
- Thay đổi giá trị constant variable trong thư viện rồi chỉ deploy lại JAR của thư viện nhưng **không biên dịch lại client** có thể khiến client tiếp tục dùng hằng số cũ. Đây là hệ quả của **constant inlining lúc biên dịch**, khác với cache của JIT.
- Một `static final` được khởi tạo runtime, chẳng hạn `Integer.parseInt("42")`, không phải compile-time constant expression, dù field vẫn chỉ được gán một lần bằng Java source hợp lệ.

Bạn có thể quan sát bytecode:

```bash
javap -c -p FinalFieldObservationDemo
```

Trong ví dụ chạy phía trên, biểu thức `Constants.ANSWER` là compile-time constant. `javap` có thể hiển thị lệnh đẩy literal `42` ở call site, thay vì một lệnh `getstatic` đọc field mỗi lần; chi tiết mnemonic và trình tự lệnh tùy bytecode do compiler phát sinh.

**Lưu ý:** `static final` và compile-time constant là hai điều kiện khác nhau. Cấm reflective write đối với `static final` trong Java 17+ không đồng nghĩa **mọi `static final`** đều được inline như một literal ngay khi biên dịch.

## 7. Các tối ưu JVM và rủi ro về hiệu năng

JVM/JIT có thể tận dụng tính ổn định của `final` để giảm số lần đọc bộ nhớ, duy trì giá trị trong thanh ghi, loại phép đọc lặp lại, thực hiện constant propagation/constant folding trong những trường hợp hợp lệ, và tổ chức lại lệnh quanh các điểm không có thay đổi hợp lệ theo mô hình ngôn ngữ.

Tuy nhiên:

- **Không có quy tắc “mọi `final` đều luôn được inline”**. Kỹ thuật chính xác tùy field, escape analysis, cấu hình JIT, phiên bản JVM và code path.
- **Không có quy tắc “`final` luôn nhanh hơn”** trên mọi workload. Giá trị của `final` trước hết nằm ở tính đúng đắn, khả năng diễn đạt bất biến và cơ hội tối ưu.
- Một hệ thống cho phép sửa `final` bằng deep reflection trong lúc ứng dụng đang chạy hạn chế những giả định tối ưu mà JVM có thể áp dụng an toàn, vì phải tính đến khả năng phá vỡ bất biến.
- Việc JDK ngày càng hạn chế reflective mutation hướng tới **integrity by default**: làm cho cam kết `final` đáng tin hơn và mở thêm không gian tối ưu về lâu dài.

Khi benchmark, tránh đánh giá bằng một vòng lặp tự viết đơn giản: warm-up, inlining, dead-code elimination, constant folding và môi trường chạy có thể làm sai kết luận. Nếu cần microbenchmark có giá trị, hãy dùng JMH cùng các điều kiện kiểm thử nhất quán. Không nên suy luận hợp đồng JMM từ kết quả đo thời gian.

## 8. Hành vi theo phiên bản JDK: phần cần kiểm tra khi nâng cấp

### 8.1. Mốc phiên bản

| Dòng JDK | Những điểm liên quan tới `final` qua Reflection |
| --- | --- |
| **JDK 8** | Mô hình JMM `final` đã tồn tại; kỹ thuật reflective mutation từng được dùng bởi một số thư viện khởi tạo đối tượng. Những thủ thuật đụng tới nội bộ JVM không phải API ổn định. |
| **JDK 9–16** | JPMS bổ sung ranh giới module và kiểm tra deep reflection; record và hidden class xuất hiện trong quá trình tiến hóa platform. Không nên suy luận quyền ghi `final` chỉ từ quyền `private`. |
| **JDK 17–25** | Strong encapsulation JDK trở nên chặt chẽ; `Field` quy định rõ không cho ghi `static final`, record final và hidden-class final bằng `setAccessible`. Một số `final` instance của class thông thường vẫn có thể được sửa phản chiếu khi đủ điều kiện. |
| **JDK 26** | **JEP 500 – Prepare to Make Final Mean Final**: mặc định phát cảnh báo về reflective mutation đối với `final` instance khi không cấp phép, chuẩn bị cho hạn chế nghiêm khắc hơn ở tương lai; bổ sung chính sách và tùy chọn launch. |
| **JDK 27 (phát hành 09/2026)** | Tiếp tục **cảnh báo** đối với reflective mutation trái chính sách theo JEP 500; tài liệu migration vẫn mô tả sự chặn bằng exception là hướng cho **phiên bản tương lai**, không nên viết rằng mọi ghi đã bị cấm mặc định trong JDK 27. |

**Phạm vi thông tin về phiên bản:** bảng dựa trên Java/JDK đã công bố đến tháng 10/2026. Nếu ứng dụng chạy trên bản update/vendor JVM cụ thể hoặc JDK mới hơn, đọc **API docs và migration notes của đúng runtime đang triển khai**.

### 8.2. JDK 26–27: cảnh báo khi mutate `final`

JDK 26 thêm chính sách final-field mutation. Nếu code từ một module ghi `final` instance thông qua deep reflection trong trường hợp không được cấp năng lực này, mặc định JVM có thể ghi cảnh báo, gồm field và mã đang thực hiện mutation. Cảnh báo được báo trên **stderr** nên test chỉ so stdout có thể không phát hiện.

Các tùy chọn được JEP 500 giới thiệu:

```text
--enable-final-field-mutation=ALL-UNNAMED
--enable-final-field-mutation=module.name
--illegal-final-field-mutation=warn
--illegal-final-field-mutation=allow
--illegal-final-field-mutation=debug
--illegal-final-field-mutation=deny
```

Ý nghĩa:

- `--enable-final-field-mutation=ALL-UNNAMED`: cấp năng lực mutation cho code trong unnamed module(s), phù hợp khi cần xử lý thư viện legacy trên classpath. Điều này **không tự mở package đích** cho deep reflection.
- `--enable-final-field-mutation=module.name`: cấp năng lực cho named module tương ứng; caller phải nằm trong module được cấp phép.
- `--illegal-final-field-mutation=warn`: chính sách mặc định ở JDK 26–27, cảnh báo đối với thao tác trái chính sách.
- `allow`: cho phép mà không báo cảnh báo thuộc chính sách này; `debug`: ghi thông tin chẩn đoán chi tiết hơn; `deny`: từ chối mutation trái chính sách, hữu ích để rà soát code trước khi chính sách mặc định siết chặt.

Để kiểm tra ví dụ trên với chính sách chặn khi chạy JDK 26–27:

```bash
java --illegal-final-field-mutation=deny FinalFieldObservationDemo
```

**Dòng cuối** của stdout có thể chuyển thành `ordinary instance final write=denied`, bởi mutation từ unnamed module không được cấp phép. Điều này không liên quan đến hai thao tác `static final` và record final: chúng **vốn bị cấm** trong Reflection chuẩn trước JDK 26.

Nếu thực sự cần cho phép phần mềm cũ thực hiện mutation trong giai đoạn chuyển tiếp:

```bash
java --enable-final-field-mutation=ALL-UNNAMED FinalFieldObservationDemo
```

Tùy chọn này phù hợp với ví dụ classpath và không có module boundary phức tạp. Trong ứng dụng module thực, việc được cấp năng lực mutation còn phải đi cùng quyền truy cập thích hợp tới package đích; **`--add-opens` và `--enable-final-field-mutation` giải quyết hai quyền khác nhau**.

**Quan trọng:** chọn `allow` hoặc cấp quyền mutation chỉ là giải pháp tương thích khi bắt buộc. Nó không tạo ra bảo đảm quan sát mới sau khi sửa `final`, không sửa được `static final`/record/hidden-class final qua `Field.set`, và không biến thiết kế mutable thành thread-safe.

### 8.3. Dự báo thay đổi mà không khẳng định quá mức

JEP 500 nói rõ mục đích là **chuẩn bị** cho một phiên bản tương lai nơi hành vi illegal final field mutation sẽ chuyển từ warning sang exception mặc định. Vì vậy:

- Không hard-code giả định “trên mọi JDK, `setAccessible(true)` sẽ cho sửa `final` instance”.
- Không hard-code giả định “từ JDK 26 mọi sửa `final` đều luôn ném exception”.
- Khi nâng cấp, chạy compatibility tests với `--illegal-final-field-mutation=deny` để tìm điểm phụ thuộc vào mutation, kiểm tra cả stderr và stack trace.
- Cập nhật framework/serializer sang bản hỗ trợ cơ chế khởi tạo hợp lệ thay vì duy trì thủ thuật trên object đã đưa vào dùng.

## 9. Các dạng vấn đề hay gặp

### 9.1. Reflection đọc được nhưng không ghi được

`field.trySetAccessible()` trả `true` chỉ nói rằng yêu cầu **suppress access checks** hợp lệ. Sau đó, `field.set(...)` vẫn có thể ném `IllegalAccessException` nếu field là non-modifiable final hoặc chính sách final mutation ngăn thao tác. Nếu package trong named module không mở cho caller thì việc bật access có thể thất bại trước đó.

**Cách xử lý:** ghi log `field.getDeclaringClass().getModule()`, `field.getModifiers()`, `field.getDeclaringClass().isRecord()`, runtime `java.version` và loại exception. Không “sửa lỗi” bằng cách xóa modifier `final` một cách tùy tiện.

### 9.2. Unit test đi qua Reflection nhưng production thấy giá trị cũ

Một phép thử chạy ngắn dưới interpreter có thể thấy cập nhật, nhưng getter production sau warm-up có thể bị tối ưu khác. Kết quả benchmark còn phụ thuộc JVM, flag và kiểu khai báo field.

**Cách xử lý:** thiết kế lại để khởi tạo đủ dữ liệu trong constructor, truyền dependency qua constructor/factory hoặc dùng cơ chế mutable hợp lệ (`volatile`, atomic reference, lock) nếu nghiệp vụ thật sự cần cập nhật.

### 9.3. Thay giá trị hằng số trong library nhưng client vẫn in giá trị cũ

Nếu `static final` là constant variable, mã client có thể đã nhúng literal từ lần compile trước. Thay JAR riêng của library không nhất thiết thay đổi code client đã được biên dịch.

**Cách xử lý:** rebuild những client phụ thuộc khi thay đổi compile-time constants công khai; tránh coi chúng như cấu hình có thể cập nhật runtime.

### 9.4. Hiểu nhầm Reflection là kênh đồng bộ hóa

`Field.set`/`get` không tự tạo ra một giao thức publish-consume an toàn chỉ vì field có modifier `final`. Một người viết vào object đã công bố, người khác đọc ở loop, có thể chạm các hạn chế quan sát và data race tùy thiết kế.

**Cách xử lý:** tách cấu hình bất biến thành object mới và công bố an toàn; với trạng thái mutable, dùng primitive đồng bộ hóa được JMM công nhận.

### 9.5. Tưởng tắt JIT sẽ giải quyết tận gốc

`-Xint` hữu ích cho một **thử nghiệm chẩn đoán** (chạy interpreted mode), nhưng không thay đổi đặc tả và không biến reflective mutation của `final` thành hành vi có hợp đồng ổn định. Tương tự, `-Xcomp` hoặc các JVM optimization flags không thay thế được thiết kế đúng.

## 10. Thiết kế thay thế an toàn

### 10.1. Bất biến thật sự: truyền qua constructor

```java
final class ImmutableConfig {
    private final String endpoint;

    ImmutableConfig(String endpoint) {
        this.endpoint = java.util.Objects.requireNonNull(endpoint);
    }

    String endpoint() {
        return endpoint;
    }
}
```

Đây là **class minh họa**, không có `main`. Giá trị được đặt khi khởi tạo và sau đó không bị thay thế.

### 10.2. Nếu cần cập nhật cấu hình runtime

```java
import java.util.concurrent.atomic.AtomicReference;

final class ConfigHolder {
    private final AtomicReference<String> endpoint =
            new AtomicReference<>("https://example.invalid");

    String getEndpoint() {
        return endpoint.get();
    }

    void changeEndpoint(String replacement) {
        endpoint.set(java.util.Objects.requireNonNull(replacement));
    }
}
```

Ở ví dụ này, **tham chiếu tới `AtomicReference` là `final`**, nhưng trạng thái được quản lý bởi đối tượng atomic có thể thay đổi đúng hợp đồng JMM. Đây là **class minh họa**, không có `main`. Trong ứng dụng thật, cần thêm validation và quản lý vòng đời tương ứng với nghiệp vụ.

### 10.3. Với serialization/deserialization

Ưu tiên framework hỗ trợ constructor/factory, record constructor, builder hoặc cơ chế đọc dữ liệu phù hợp. Nếu thư viện legacy bắt buộc ghi `final` trong lúc tái dựng object, hãy giới hạn thao tác **trước khi object được công bố hoặc đọc**, kiểm tra rõ quyền/module/runtime và chuẩn bị migration theo JEP 500. Không sửa object sau khi nó đã được sử dụng rồi trông đợi mọi getter và thread tự thấy giá trị mới.

## 11. Checklist chẩn đoán và kiểm thử

1. **Xác định loại field:** instance hay static, `final` hay không, thuộc class thường, record hay hidden class? Dùng `getModifiers()` và `Modifier.isFinal(...)`.
2. **Xác định quyền:** caller cùng class/module hay khác module? Package đích có open không? `setAccessible(true)` có thành công không?
3. **Xác định phiên bản runtime:** `System.getProperty("java.version")` và các JVM flags đang dùng; không suy đoán từ source compatibility `--release 17`.
4. **Phân biệt ba phép kiểm tra:** permission to write, observed reflective read, observed compiled getter. Không xem chúng là đồng nhất.
5. **Kiểm tra hằng số compile-time:** field `static final` có thuộc kiểu primitive/`String` và constant expression không? Client có phải rebuild không?
6. **Kiểm tra điểm công bố:** object có bị truy cập trước/khi đang thay field không? Có race condition không?
7. **Dùng môi trường nâng cấp:** thử JDK 26–27 với policy `--illegal-final-field-mutation=deny`, xem exception, stderr và dependency nào thực hiện mutation.
8. **Chọn sửa thiết kế:** constructor/factory hoặc cơ chế mutable có synchronization; coi reflective final mutation là trường hợp tương thích cần giảm dần.

## 12. Nguồn đặc tả và tài liệu kiểm chứng

- Java Language Specification, `17.5 *final Field Semantics* và `17.5.3 *Subsequent Modification of final Fields*: https://docs.oracle.com/javase/specs/jls/se26/html/jls-17.html
- Java SE 17, `java.lang.reflect.Field`, mục `setAccessible` và `set`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html
- Oracle JDK 26 Migration Guide, *Preparing for final Field Mutation Restrictions*: https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html
- Oracle JDK 27 Migration Guide, *Significant Changes*: https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html

**Ghi nhớ:** `final` không chỉ là cờ modifier; đó là cam kết thiết kế và cơ sở cho quy tắc bộ nhớ cùng tối ưu. Một reflective write có thể được runtime chấp nhận trong hoàn cảnh nhất định nhưng **không tạo bảo đảm quan sát đáng tin** trên object đã dùng. Vì vậy phải phân biệt khả năng ghi, khả năng quan sát và hiệu ứng tối ưu; đồng thời kiểm tra chính sách mới của JDK 26–27 khi nâng cấp.