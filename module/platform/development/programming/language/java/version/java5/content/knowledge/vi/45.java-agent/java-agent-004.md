# Instrumentation và khả năng JVM cung cấp

## 1. Instrumentation giải quyết việc gì?

Một công cụ theo dõi ứng dụng đôi khi cần làm việc ở cấp JVM: biết những lớp nào đã được nạp, bổ sung mã đo đạc vào phương thức, hoặc ước lượng kích thước một đối tượng. Chỉ có mã nghiệp vụ và reflection thông thường không cung cấp đầy đủ các thao tác đó.

`java.lang.instrument.Instrumentation` là interface mà JVM cung cấp cho Java agent. Nó là cầu nối tới các dịch vụ instrumentation của JVM, không phải thư viện tự động phân tích hay tự động chỉnh sửa mọi lớp.

Ba tầng cần tách biệt:

```text
JVM cung cấp dịch vụ
    -> agent nhận Instrumentation
        -> agent kiểm tra khả năng và điều kiện
            -> agent chọn thao tác phù hợp
```

Có đối tượng `Instrumentation` không có nghĩa mọi thao tác đều được hỗ trợ. Một thao tác còn có thể phụ thuộc cấu hình agent, khả năng JVM, lớp đích và nội dung thay đổi.

Cơ chế agent xuất hiện từ Java 5, nhưng bài này trình bày cách dùng còn áp dụng trên Java hiện đại; ví dụ biên dịch với `--release 17`. Một số API như thao tác với Java module xuất hiện ở các phiên bản sau Java 5.

## 2. Nhận đối tượng từ JVM

Cách thông dụng khi khởi động ứng dụng là điểm vào:

```java
public static void premain(String options, Instrumentation inst)
```

Đây là chữ ký minh họa; cần nhập `java.lang.instrument.Instrumentation`. JVM truyền đối tượng thật vào `inst` khi nạp agent bằng `-javaagent`. Với cơ chế nạp agent vào JVM đang chạy, điểm vào hai tham số là `agentmain(String, Instrumentation)`.

Không dùng `new Instrumentation()`; đây là interface, và tự viết một lớp triển khai nó cũng không tạo được quyền điều khiển JVM. API không có một phương thức tĩnh công khai kiểu `Instrumentation.getInstance()` cho mọi ứng dụng gọi tùy ý.

Agent có thể giữ tham chiếu nhận được để dùng sau khi điểm vào đã trả về. Tuy nhiên, việc nhận được đối tượng không thay thế thiết kế đồng bộ, quản lý vòng đời hoặc xử lý lỗi của chính công cụ. Hợp đồng khởi động xem [đặc tả java.lang.instrument](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/package-summary.html).

## 3. Bản đồ các nhóm khả năng

| Nhu cầu | API tiêu biểu | Điểm cần phân biệt |
| --- | --- | --- |
| Đăng ký xử lý bytecode | `addTransformer`, `removeTransformer` | Đăng ký bộ biến đổi khác với tự sửa một lớp đã nạp |
| Biến đổi lại lớp đã nạp | `retransformClasses` | Chạy lại quá trình biến đổi theo hợp đồng của các bộ biến đổi |
| Cung cấp định nghĩa lớp thay thế | `redefineClasses` | Agent đưa bytecode mới qua `ClassDefinition` |
| Kiểm kê lớp | `getAllLoadedClasses`, `getInitiatedClasses` | Lớp đã nạp khác với đối tượng đang sống trên heap |
| Ước lượng bộ nhớ | `getObjectSize` | Kích thước một đối tượng khác tổng đồ thị đối tượng |
| Bổ sung nơi tìm lớp hỗ trợ | `appendToBootstrapClassLoaderSearch`, `appendToSystemClassLoaderSearch` | Khả năng nhìn thấy lớp phụ thuộc bộ nạp lớp |
| Điều chỉnh quan hệ module | `isModifiableModule`, `redefineModule` | Mở rộng quan hệ đọc/xuất/mở và dịch vụ |
| Hỗ trợ công cụ bao quanh phương thức native | `isNativeMethodPrefixSupported`, `setNativeMethodPrefix` | Không phải API sửa trực tiếp mã máy native |

Bảng là bản đồ để chọn API, không phải lời hứa rằng mọi JVM đều hỗ trợ mọi thao tác.

### Đăng ký bộ biến đổi

`addTransformer(transformer)` tương đương đăng ký với `canRetransform=false`. Dạng `addTransformer(transformer, true)` yêu cầu khả năng retransformation.

Bộ biến đổi nhận dữ liệu class file và trả về mảng byte mới, hoặc `null` khi không thay đổi. Không sửa trực tiếp mảng đầu vào. Đăng ký xong không khiến tất cả lớp đã nạp trước đó tự chạy lại bộ biến đổi; muốn tác động các lớp đó phải chọn cơ chế phù hợp và kiểm tra điều kiện.

Gỡ bằng `removeTransformer` dừng việc đăng ký cho tương lai; không tự khôi phục các lớp đã bị thay đổi. Do nạp lớp có thể diễn ra đồng thời, bộ biến đổi còn phải chịu được lời gọi đang diễn ra khi bị gỡ. Chi tiết xem [hợp đồng ClassFileTransformer](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html).

## 4. Khả năng tùy chọn: manifest, JVM và lớp đích

Ba khả năng tùy chọn thường gặp:

| Khai báo trong manifest | Kiểm tra bằng Instrumentation |
| --- | --- |
| `Can-Redefine-Classes: true` | `isRedefineClassesSupported()` |
| `Can-Retransform-Classes: true` | `isRetransformClassesSupported()` |
| `Can-Set-Native-Method-Prefix: true` | `isNativeMethodPrefixSupported()` |

Nếu không khai báo, giá trị mặc định của các thuộc tính trên là `false`. Khai báo `true` thể hiện agent yêu cầu khả năng đó; vẫn cần JVM hỗ trợ. Không xem manifest như cách ép JVM thực hiện một tính năng mà nó không cung cấp.

Cũng không có setter để gọi `setRetransformSupported(true)` sau khi khởi động. Muốn đổi khai báo agent trong ví dụ, cần đóng gói JAR khác và khởi động lại tiến trình.

Đối với một lớp đã nạp, kiểm tra thêm `isModifiableClass(target)`. Hai câu hỏi độc lập:

1. Agent/JVM có hỗ trợ loại thao tác này không?
2. Lớp đích có thuộc loại được phép sửa đổi không?

`isModifiableClass(target)==true` không kéo theo `isRetransformClassesSupported()==true`, và chiều ngược lại cũng không đúng. Lớp mảng và lớp biểu diễn kiểu nguyên thủy không thể sửa đổi theo API này.

Ví dụ điều kiện bảo vệ, chỉ là đoạn mã đặt trong agent đã có `inst` và `target`:

```java
if (!inst.isRetransformClassesSupported()) {
    throw new IllegalStateException("JVM/agent khong ho tro retransform");
}
if (!inst.isModifiableClass(target)) {
    throw new IllegalArgumentException("Lop dich khong the sua doi");
}
// Còn cần đăng ký bộ biến đổi phù hợp và bảo đảm bytecode hợp lệ.
inst.retransformClasses(target);
```

Vượt qua hai phép kiểm tra vẫn chưa chứng minh thay đổi bytecode hợp lệ. Phải tôn trọng cấu trúc lớp, phiên bản class file và quy tắc liên kết của JVM.

## 5. Giới hạn khi thay đổi lớp đã nạp

`redefineClasses` nhận các `ClassDefinition` gồm lớp đích và bytecode thay thế. `retransformClasses` yêu cầu chạy lại quá trình biến đổi cho các lớp đã nạp. Không coi hai API là hai tên cho một thao tác giống hệt nhau.

Khi retransformation diễn ra, JVM gọi lại các bộ biến đổi có khả năng retransformation; với bộ biến đổi không có khả năng đó, kết quả biến đổi trước được sử dụng lại theo hợp đồng API. Vì vậy, không giả định mọi bộ biến đổi đều được gọi lại, cũng không giả định mỗi lần chỉ nối thêm mã vào bytecode kết quả của lần trước.

Trên hợp đồng thay đổi lớp tiêu chuẩn, không thể tùy ý thêm/xóa trường hoặc phương thức hay thay quan hệ kế thừa của một lớp đã nạp. Thay nội dung phương thức vẫn cần class file hợp lệ và tuân thủ các hạn chế cụ thể. Khả năng mở rộng riêng của một JVM không phải cam kết di động của `Instrumentation`.

Khi một phương thức đang có khung thực thi hoạt động, khung đó tiếp tục dùng mã cũ; các lần gọi mới dùng định nghĩa mới. Việc thay định nghĩa không chạy lại bộ khởi tạo lớp, không tự đặt lại trường tĩnh và không tạo lại các đối tượng đang tồn tại. Các giới hạn cấu trúc được quy định ở [JVM TI RedefineClasses](https://docs.oracle.com/en/java/javase/25/docs/specs/jvmti.html#RedefineClasses).

Ví dụ, đổi phần thân `calculate()` không có nghĩa một tác vụ đang chạy trong `calculate()` lập tức chuyển sang phần thân mới giữa chừng.

## 6. Kiểm kê lớp và đo bộ nhớ đúng ý nghĩa

### Lớp đã nạp không phải danh sách đối tượng

`getAllLoadedClasses()` trả về mảng các lớp hiện đã được nạp trong JVM, bao gồm lớp mảng và lớp ẩn. Đây không phải danh sách tệp `.class` có sẵn trên đĩa, cũng không phải danh sách mọi đối tượng của những lớp đó.

`getInitiatedClasses(loader)` trả về các lớp mà bộ nạp được ghi nhận là bộ nạp khởi phát. Một lớp có thể được bộ nạp cha định nghĩa nhưng được tìm thông qua bộ nạp con; “khởi phát” khác “định nghĩa”. Truyền `null` để hỏi các lớp có thể tìm theo cơ chế tương ứng của bootstrap loader. Không dùng kết quả này như bảng mọi lớp do riêng loader đó định nghĩa.

Kết quả kiểm kê cũng không tự bảo đảm lớp có thể sửa đổi; kiểm tra từng lớp bằng API phù hợp.

### Kích thước một đối tượng không phải toàn bộ dữ liệu nó giữ

`getObjectSize(value)` trả về ước lượng phụ thuộc cách triển khai JVM cho đối tượng được truyền vào. Ví dụ:

```java
byte[] data = new byte[16];
long estimate = inst.getObjectSize(data);
```

Đoạn mã giả định đang ở nơi đã có `inst`. Con số không chỉ là `16` byte dữ liệu: đối tượng mảng còn có chi phí quản lý và căn chỉnh tùy JVM.

Nếu đo một đối tượng có trường tham chiếu tới mảng lớn, không được coi kết quả là tổng kích thước cả mảng được tham chiếu. Tương tự, đo `ArrayList` không tự cộng toàn bộ vùng chứa bên trong và các phần tử của nó. Muốn đo toàn đồ thị tham chiếu cần một công cụ/thuật toán khác, có xử lý tham chiếu dùng chung và chu kỳ.

API này không cung cấp phép liệt kê mọi đối tượng trên heap hay xác định chính xác bộ nhớ được thu hồi khi bỏ một tham chiếu. Con số ước lượng phù hợp để khảo sát trong cùng môi trường; không dùng một giá trị làm hằng số chung cho mọi JVM. `getObjectSize(null)` ném `NullPointerException`.

## 7. Ví dụ chạy được: khảo sát khả năng của agent

Ví dụ dưới đây không sửa bytecode; nó cho thấy JVM cung cấp những gì cho một agent cụ thể.

Tạo các tệp:

```text
src/agent/demo/agent/CapabilityAgent.java
src/app/demo/app/Main.java
agent-manifest.mf
```

### Agent

Tệp `src/agent/demo/agent/CapabilityAgent.java`:

```java
package demo.agent;

import java.lang.instrument.Instrumentation;

public final class CapabilityAgent {
    public static void premain(String options, Instrumentation inst) {
        System.out.println("redefine=" + inst.isRedefineClassesSupported());
        System.out.println("retransform=" + inst.isRetransformClassesSupported());
        System.out.println("nativePrefix=" + inst.isNativeMethodPrefixSupported());
        System.out.println("arrayModifiable=" + inst.isModifiableClass(byte[].class));
        System.out.println("primitiveModifiable=" + inst.isModifiableClass(int.class));

        byte[] sample = new byte[16];
        System.out.println("size(byte[16])=" + inst.getObjectSize(sample));
    }
}
```

### Ứng dụng

Tệp `src/app/demo/app/Main.java`:

```java
package demo.app;

public final class Main {
    public static void main(String[] args) {
        System.out.println("main=started");
    }
}
```

### Manifest tối thiểu

Tệp `agent-manifest.mf`, lưu không có BOM và kết thúc bằng xuống dòng:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.CapabilityAgent

```

### Biên dịch và chạy

Dùng JDK 17 trở lên, tại thư mục chứa `src` và manifest:

```shell
javac --release 17 -d out/agent src/agent/demo/agent/CapabilityAgent.java
javac --release 17 -d out/app src/app/demo/app/Main.java
jar --create --file capabilities.jar --manifest agent-manifest.mf -C out/agent .
java "-javaagent:capabilities.jar" -cp out/app demo.app.Main
```

Một lần chạy trên OpenJDK Zulu 24.0.2, JVM 64 bit với cấu hình mặc định, cho stdout:

```text
redefine=false
retransform=false
nativePrefix=false
arrayModifiable=false
primitiveModifiable=false
size(byte[16])=32
main=started
```

Ba dòng đầu là `false` vì manifest không yêu cầu các khả năng tùy chọn. Hai dòng tiếp theo thể hiện giới hạn của lớp mảng và kiểu nguyên thủy. Con số `32` là kết quả của môi trường chạy nêu trên, **không phải giá trị bắt buộc** trên mọi JDK hoặc cấu hình JVM.

Để khảo sát các khả năng tùy chọn, tạo tệp khác tên `enabled-manifest.mf`:

```text
Manifest-Version: 1.0
Premain-Class: demo.agent.CapabilityAgent
Can-Redefine-Classes: true
Can-Retransform-Classes: true
Can-Set-Native-Method-Prefix: true

```

Đóng gói từ cùng lớp đã biên dịch:

```shell
jar --create --file capabilities-enabled.jar --manifest enabled-manifest.mf -C out/agent .
java "-javaagent:capabilities-enabled.jar" -cp out/app demo.app.Main
```

Trên môi trường thử nghiệm vừa nêu, ba dòng đầu chuyển thành `true`; các dòng còn lại giữ nguyên. Trên JVM khác, đọc kết quả thực tế, không sửa kỳ vọng thành `true` một cách máy móc. Khả năng được bật cũng không tự kích hoạt việc sửa lớp: ví dụ chưa đăng ký bộ biến đổi và chưa gọi redefine/retransform.

## 8. Bộ nạp lớp, module và phương thức native

Các API sau thường cần cho công cụ instrumentation nâng cao; hiểu vai trò trước khi sử dụng:

- `appendToBootstrapClassLoaderSearch` và `appendToSystemClassLoaderSearch` bổ sung JAR chứa lớp hỗ trợ vào nơi tìm kiếm tương ứng. Chúng không thay thế một lớp cùng tên đã được nạp và không bảo đảm mọi bộ nạp tùy biến đều nhìn thấy lớp đó. Lớp hỗ trợ đặt ở bootstrap phải có các phụ thuộc nhìn thấy được từ bootstrap; tránh đưa cả thư viện ứng dụng vào đây.
- `redefineModule` có thể mở rộng các quan hệ đọc module, xuất/mở package và dịch vụ mà module dùng/cung cấp. Nó không thu hẹp những tập hợp đó. Cần phân biệt truy cập qua quan hệ module với khả năng tìm thấy một lớp qua bộ nạp; giải quyết được một phía chưa chắc giải quyết phía còn lại.
- `setNativeMethodPrefix` hỗ trợ cơ chế ánh xạ tên phương thức native khi công cụ tạo phương thức bao quanh. Phương thức native không có bytecode Java để sửa trực tiếp; đây không phải API chỉnh mã máy tùy ý.

Các chữ ký và điều kiện chi tiết của những nhóm API này nằm trong [tài liệu Instrumentation](https://docs.oracle.com/en/java/javase/25/docs/api/java.instrument/java/lang/instrument/Instrumentation.html). Không gọi chúng chỉ vì muốn “bật hết quyền”; cần xác định chính xác lớp hỗ trợ, quan hệ truy cập hoặc khả năng công cụ thực sự cần.

## 9. Lỗi tư duy thường gặp và cách kiểm chứng

| Nhận định sai | Cách suy luận đúng |
| --- | --- |
| Có `Instrumentation` thì sửa được mọi lớp | Kiểm tra khả năng agent/JVM, lớp đích và tính hợp lệ của thay đổi |
| Manifest có `true` là đủ | Đọc kết quả API `is...Supported()` của đối tượng đang dùng |
| Đăng ký bộ biến đổi là mọi lớp cũ đổi ngay | Lớp đã nạp cần cơ chế xử lý riêng với điều kiện tương ứng |
| Gỡ bộ biến đổi sẽ hoàn tác mã đã sửa | Gỡ đăng ký không khôi phục định nghĩa lớp trước đó |
| `getObjectSize` đo toàn bộ dữ liệu liên quan | Nó ước lượng đối tượng truyền vào; không duyệt toàn đồ thị tham chiếu |
| Danh sách lớp đã nạp cho biết mọi đối tượng sống | Kiểm kê lớp và kiểm kê đối tượng là hai vấn đề khác nhau |
| Sửa lớp sẽ khởi tạo lại trạng thái | Không tự chạy lại khởi tạo lớp hoặc tạo lại đối tượng |

Tự thực hành:

1. Chạy hai manifest của ví dụ và giải thích vì sao cùng bytecode agent cho kết quả khả năng khác nhau.
2. Đổi mảng thành `new byte[17]`; quan sát kích thước có thể chịu ảnh hưởng căn chỉnh, không ép mức tăng đúng một byte.
3. Thêm phép kiểm tra `isModifiableClass(CapabilityAgent.class)`; đối chiếu nó với kết quả `isRetransformClassesSupported()` ở manifest tối thiểu.
4. Nêu đủ ba điều kiện trước khi tác động một lớp đã nạp: hỗ trợ loại thao tác, lớp sửa đổi được và thay đổi hợp lệ.
