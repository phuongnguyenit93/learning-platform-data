# Can-Set-Native-Method-Prefix và isNativeMethodPrefixSupported

> **Ý chính:** `Can-Set-Native-Method-Prefix` là một **khả năng tùy chọn** của Java instrumentation, được yêu cầu trong manifest của agent. `Instrumentation.isNativeMethodPrefixSupported()` kiểm tra khả năng đó trong cấu hình JVM hiện tại. Khi có hỗ trợ, `Instrumentation.setNativeMethodPrefix(transformer, prefix)` cho phép JVM **thử lại việc liên kết một phương thức `native` với triển khai JNI theo quy tắc tiền tố**. Cơ chế này phục vụ agent muốn tạo **Java wrapper có bytecode** xung quanh một phương thức native vốn **không có Java bytecode để chèn trực tiếp**. Khai báo cờ hoặc gọi API **không tự biến đổi bytecode và không tự tạo wrapper**.

## 1. Vì sao instrumentation cần một "native method prefix"?

Một phương thức Java thông thường có phần thân bytecode, nên một `ClassFileTransformer` có thể tạo thêm hướng đi đo đạc: ghi log, đo thời gian, đếm lời gọi và chuyển tiếp đến phần thân nguyên bản. Ngược lại, một phương thức khai báo `native` không có `Code` attribute chứa Java bytecode; phần thực thi nằm ở thư viện hoặc runtime native được liên kết qua JNI.

Ví dụ lớp ứng dụng ban đầu có:

~~~java
package com.example;

public class NativeCounter {
    public native long read(long key);
}
~~~

Đây là **mảnh mã minh họa**, chưa phải chương trình hoàn chỉnh vì cần một thư viện JNI cung cấp triển khai. Nếu JNI dùng cách tìm tên symbol tự động, mã native tương ứng có thể xuất một hàm kiểu:

~~~c
/* Minh họa JNI cho phương thức instance, không phải chương trình C độc lập. */
JNIEXPORT jlong JNICALL
Java_com_example_NativeCounter_read(JNIEnv *env, jobject self, jlong key);
~~~

Agent không thể chèn Java bytecode ngay vào phần thân `native read`. Thay vào đó, trong **lần định nghĩa lớp ban đầu**, transformer có thể tạo cấu trúc tương đương:

~~~java
package com.example;

public class NativeCounter {
    // Java wrapper do transformer sinh ra, có bytecode để đo đạc.
    public long read(long key) {
        long started = System.nanoTime();
        try {
            return $observe$read(key);
        } finally {
            System.out.println("elapsed-ns=" + (System.nanoTime() - started));
        }
    }

    // Native entry đã được đổi tên, giữ nguyên chữ ký tham số/kết quả.
    private native long $observe$read(long key);
}
~~~

Đây cũng là **minh họa kết quả biến đổi class file**: một transformer thực sự còn phải sinh bytecode hợp lệ, xử lý constant pool, stack frames, exception table và tính tương thích của method. Việc viết hai lớp `NativeCounter` trùng tên vào hai tệp Java không thay thế cho một transformer, và ví dụ không chạy độc lập nếu thiếu JNI library.

Vấn đề mới xuất hiện: thư viện native đã cung cấp symbol cho `read`, **không có** symbol mới cho `$observe$read`. Nếu JVM chỉ tìm tên native mới, lời gọi có thể kết thúc bằng `UnsatisfiedLinkError`. Native method prefix giải quyết chỗ nối này: khi tìm bình thường thất bại, JVM được phép thử lại **bỏ tiền tố** theo quy tắc của transformer, từ đó tìm lại triển khai JNI gốc.

~~~text
Ứng dụng gọi NativeCounter.read(key)
         |
         v
Java wrapper read() có bytecode
  - bắt đầu đo thời gian
  - gọi native $observe$read(key)
         |
         v
JVM tìm JNI implementation cho $observe$read
         |
         +--> Tìm bình thường thành công: dùng implementation đó
         |
         +--> Không tìm được: thử quy tắc tiền tố đã đăng ký
                  |
                  v
             Tìm triển khai JNI gốc của read
                  |
                  v
              Trả kết quả cho wrapper
                  |
                  v
             Wrapper hoàn tất đo đạc
~~~

**Vai trò của từng phần:** transformer tạo wrapper và đổi tên method; `setNativeMethodPrefix` cấu hình cách JVM *thử lại resolution*; `isNativeMethodPrefixSupported` cho biết cấu hình này có được phép sử dụng hay không. Cơ chế không chặn tùy ý mọi lời gọi JNI, không chỉnh sửa mã máy trong thư viện native, và không thay thế một lớp có bytecode hợp lệ.

## 2. Ba lớp điều kiện: manifest, JVM và transformer

Có hai thành phần public API và một thuộc tính manifest cần nhớ chính xác:

| Thành phần | Kiểu/đầu vào | Ý nghĩa |
| --- | --- | --- |
| `Can-Set-Native-Method-Prefix` | Thuộc tính **main section** của `META-INF/MANIFEST.MF`, thường nhận `true` hoặc `false` | Agent **yêu cầu** quyền dùng tính năng đặt tiền tố native |
| `Instrumentation.isNativeMethodPrefixSupported()` | Phương thức không tham số, trả `boolean` | Cho biết cấu hình JVM hiện tại thực sự cho phép đặt tiền tố |
| `Instrumentation.setNativeMethodPrefix(ClassFileTransformer, String)` | Phương thức `void` | Gắn quy tắc tiền tố cho **một transformer đã đăng ký** |

Ví dụ manifest cho **startup agent** dùng `-javaagent`:

~~~text
Manifest-Version: 1.0
Premain-Class: com.example.agent.NativeProbeAgent
Can-Set-Native-Method-Prefix: true
~~~

Lưu manifest dưới dạng văn bản với dòng kết thúc hợp lệ. `Premain-Class` là lớp chứa `premain` và bắt buộc khi khởi động bằng `-javaagent`. Nếu agent được attach vào JVM đang chạy, manifest còn cần `Agent-Class` trỏ tới lớp chứa `agentmain`; thuộc tính `Can-Set-Native-Method-Prefix` vẫn nói về khả năng native prefix. Việc nạp agent động có các quy tắc và chính sách riêng, không làm thay đổi ý nghĩa của ba thành phần trên.

Quy tắc hỗ trợ quan trọng:

1. Thuộc tính `Can-Set-Native-Method-Prefix` là tùy chọn. **Thiếu thuộc tính → mặc định `false`**.
2. Giá trị `true` (không phân biệt chữ hoa/thường) là cách yêu cầu khả năng này; giá trị khác `true` được xem là `false`.
3. **Manifest `true` là điều kiện cần nhưng chưa đủ**: JVM cũng phải hỗ trợ khả năng đó. Không giả định mọi nhà cung cấp JVM đều bật.
4. `isNativeMethodPrefixSupported()` phải là điểm kiểm tra trong mã agent. Với một lần tạo JVM, những lần gọi liên tiếp tới phương thức này trả cùng một đáp án theo hợp đồng API.
5. `Can-Set-Native-Method-Prefix` **khác** `Can-Retransform-Classes` và `Can-Redefine-Classes`. Ba capability độc lập; khai báo một cờ không tự kích hoạt hai cờ còn lại.

Bảng quyết định:

| Manifest | JVM có khả năng native prefix? | `isNativeMethodPrefixSupported()` | Hướng xử lý |
| --- | --- | --- | --- |
| Không có thuộc tính hoặc `false` | Bất kỳ | `false` trong cấu hình agent không yêu cầu capability | Không gọi `setNativeMethodPrefix`; nếu cần JNI wrapper phải thay đổi kế hoạch |
| `true` | Không | `false` | Bỏ tính năng tùy chọn hoặc báo lỗi cấu hình nếu tính năng bắt buộc |
| `true` | Có | `true` | Đăng ký transformer, đặt prefix rồi triển khai biến đổi đúng cách |

Giá trị `true` **không có nghĩa** JVM đã liên kết một thư viện JNI hay agent đã thực sự đo được lời gọi native.

## 3. Thứ tự gọi `setNativeMethodPrefix` và các lỗi API

Luồng khởi tạo thông thường trong `premain(String, Instrumentation)` hoặc `agentmain(String, Instrumentation)`:

~~~text
Nhận Instrumentation từ JVM
    |
    v
isNativeMethodPrefixSupported()?
    |
    +-- false --> bỏ qua hoặc dừng có chẩn đoán
    |
    +-- true --> khởi tạo ClassFileTransformer
                      |
                      v
              addTransformer(transformer)
                      |
                      v
              setNativeMethodPrefix(transformer, prefix)
                      |
                      v
              JVM định nghĩa các lớp mà transformer nhắm đến
                      |
                      v
              Transformer tạo Java wrapper + native method có prefix
~~~

**Bắt buộc `addTransformer` trước `setNativeMethodPrefix`.** Gọi `setNativeMethodPrefix` cho một transformer chưa đăng ký là lỗi, ngay cả khi JVM báo capability `true`. Tên prefix phải khớp chính xác cách transformer đổi tên method. Có thể dùng ví dụ `"$agent$"` hoặc một chuỗi khó đụng tên ứng dụng hơn, chẳng hạn `"$$$TraceToolNative$$$_"`.

Các exception được đặc tả:

| Tình huống | Exception | Ý nghĩa/sửa chữa |
| --- | --- | --- |
| `transformer == null` | `NullPointerException` | Cung cấp đối tượng transformer có thật |
| Cấu hình không hỗ trợ tính năng | `UnsupportedOperationException` | Kiểm tra manifest, JVM và kết quả `isNativeMethodPrefixSupported()` |
| Transformer chưa được đăng ký | `IllegalArgumentException` | Gọi `addTransformer` với **chính instance** đó trước |
| `prefix == null` hoặc `prefix.isEmpty()` | **Không phải lỗi vì riêng prefix** | Vô hiệu hóa quy tắc thử lại native resolution cho transformer ấy |

Lưu ý: nếu một lời gọi đồng thời vi phạm nhiều điều kiện (chẳng hạn cấu hình không hỗ trợ **và** transformer không đăng ký), **đừng phụ thuộc thứ tự exception** giữa các JVM. Trước hết hãy kiểm tra capability và thứ tự đăng ký. Hàm `setNativeMethodPrefix` trả về `void`; để xác minh hiệu quả thực sự của native wrapper, phải kiểm thử lớp đã transform cùng thư viện JNI tương ứng.

**Prefix không tự áp dụng cho tất cả transformer trong JVM.** Mỗi `ClassFileTransformer` có prefix riêng; nhiều agent có thể cùng tồn tại, nên đặt tên đủ đặc thù để giảm va chạm, kiểm thử đúng thứ tự biến đổi và không tạo lại transformer vô tình.

## 4. Ví dụ Java 17+ chạy thật: bật/tắt capability và cấu hình prefix

Thí nghiệm này **không yêu cầu JNI hoặc thư viện ngoài JDK**. Nó kiểm chứng rõ ràng: manifest có/không có cờ; kết quả `isNativeMethodPrefixSupported()`; lỗi trước khi đăng ký; việc thiết lập rồi vô hiệu hóa prefix. Transformer trong demo **không sửa bytecode**, do đó không có native wrapper thực tế. Đây là kiểm thử **API/capability**, không phải kiểm thử việc chuyển tiếp sang JNI.

Tạo năm tệp trong **cùng một thư mục**, biên dịch bằng JDK 17+.

**Tệp `PrefixNoopTransformer.java`**

~~~java
import java.lang.instrument.ClassFileTransformer;

public final class PrefixNoopTransformer implements ClassFileTransformer {
    // Demo: không đổi bytecode. Java 17 có các transform method mặc định.
}
~~~

**Tệp `PrefixProbeAgent.java`**

~~~java
import java.lang.instrument.Instrumentation;

public final class PrefixProbeAgent {
    public static void premain(String options, Instrumentation inst) {
        boolean supported = inst.isNativeMethodPrefixSupported();
        System.out.println("native-prefix-supported=" + supported);

        if (!supported) {
            System.out.println("set-prefix-skipped");
            return;
        }

        PrefixNoopTransformer transformer = new PrefixNoopTransformer();
        try {
            inst.setNativeMethodPrefix(transformer, "$probe$");
            System.out.println("unexpected-success");
        } catch (IllegalArgumentException expected) {
            System.out.println("unregistered-transformer=IllegalArgumentException");
        }

        inst.addTransformer(transformer);
        try {
            inst.setNativeMethodPrefix(transformer, "$probe$");
            System.out.println("prefix-configured");
            inst.setNativeMethodPrefix(transformer, "");
            System.out.println("prefix-disabled");
        } finally {
            System.out.println("transformer-removed=" + inst.removeTransformer(transformer));
        }
    }
}
~~~

Với bản production, không nên cố ý gọi `setNativeMethodPrefix` trước khi đăng ký. Đoạn đó chỉ nhằm chứng minh `IllegalArgumentException`. Khối `finally` thu hồi transformer mà demo đã cài; đối với agent thực, bạn chỉ thu hồi khi tính năng cần dừng.

**Tệp `PrefixApp.java`**

~~~java
public final class PrefixApp {
    public static void main(String[] args) {
        System.out.println("application-main");
    }
}
~~~

**Tệp `enabled.mf`**

~~~text
Manifest-Version: 1.0
Premain-Class: PrefixProbeAgent
Can-Set-Native-Method-Prefix: true
~~~

**Tệp `disabled.mf`**

~~~text
Manifest-Version: 1.0
Premain-Class: PrefixProbeAgent
~~~

Trong ví dụ, `disabled.mf` không có cờ, nên mặc định bằng `false`. Nếu muốn mô phỏng cấu hình tường minh bị tắt, thay bằng `Can-Set-Native-Method-Prefix: false`.

### Biên dịch, đóng gói và chạy

~~~bash
javac --release 17 PrefixNoopTransformer.java PrefixProbeAgent.java PrefixApp.java

jar --create --file enabled-agent.jar --manifest enabled.mf PrefixProbeAgent.class PrefixNoopTransformer.class
jar --create --file disabled-agent.jar --manifest disabled.mf PrefixProbeAgent.class PrefixNoopTransformer.class

java -javaagent:enabled-agent.jar PrefixApp
java -javaagent:disabled-agent.jar PrefixApp
~~~

**Phải đóng gói cả `PrefixProbeAgent.class` và `PrefixNoopTransformer.class`** trong agent JAR. Để xác thực bạn đang chạy đúng file, dùng `jar --list --file enabled-agent.jar`. Tên của `Premain-Class` nằm trong manifest cần khớp lớp đã đóng gói.

Với **HotSpot/OpenJDK hỗ trợ capability** và JAR `enabled-agent.jar`, stdout:

~~~text
native-prefix-supported=true
unregistered-transformer=IllegalArgumentException
prefix-configured
prefix-disabled
transformer-removed=true
application-main
~~~

Với `disabled-agent.jar`, stdout:

~~~text
native-prefix-supported=false
set-prefix-skipped
application-main
~~~

Các kết quả này được kiểm chứng bằng biên dịch `--release 17` và chạy trên OpenJDK 24. Nếu JVM khác không hỗ trợ native prefix dù manifest là `true`, nhánh `supported=false` sẽ được thực thi; **đó là kết quả hợp lệ** theo API, không phải sai cú pháp Java.

Giải thích:

- `isNativeMethodPrefixSupported()` phản ánh cả JVM và manifest đã khai báo.
- Khi hỗ trợ, gọi `setNativeMethodPrefix` trước `addTransformer` gây `IllegalArgumentException` như dự kiến.
- Sau `addTransformer`, API nhận `"$probe$"`; chuỗi rỗng ở lời gọi sau tắt cơ chế thử lại với transformer đó.
- `removeTransformer` trả về `true` vì transformer có đăng ký. Nó không có nghĩa một phương thức native nào đã được instrument.
- `application-main` cho biết `premain` đã kết thúc bình thường rồi JVM chạy ứng dụng.

Nếu muốn thử thêm lỗi unsupported có kiểm soát, có thể gọi `setNativeMethodPrefix` trong một agent mà `isNativeMethodPrefixSupported()` là `false` và bắt riêng `UnsupportedOperationException`; **không làm việc đó trong code production** vì chỉ tạo ra lỗi đã được báo trước.

## 5. JVM thực hiện native method resolution với prefix ra sao?

Hai đường liên kết JNI phổ biến có cùng mục tiêu nhưng cách tìm tên khác nhau. Cả hai đều xuất phát từ việc **tìm bình thường không thành công**, sau đó thử quy tắc tiền tố, chứ không luôn ép mọi lời gọi native chuyển sang symbol khác.

### 5.1. JNI automatic name resolution

Giả sử transformer đã tạo cặp method:

~~~java
public long read(long key) {
    return $observe$read(key);
}

private native long $observe$read(long key);
~~~

Mã này chỉ minh họa hai method **trong cùng class** sau biến đổi. Nếu library đã xuất tên JNI tương ứng với `read` gốc, JVM trước tiên thử resolution thông thường cho `$observe$read`. Khi không tìm được, nó có thể bỏ `$observe$` nhờ prefix đã đăng ký rồi thử lại theo `read`. Nhờ đó chương trình có wrapper Java mà vẫn gọi được native implementation gốc.

Không được suy ra việc đổi tên Java đồng nghĩa phải sửa `JNI_OnLoad`, phải đổi tên thư viện `.dll`/`.so`, hoặc phải biên dịch lại mọi symbol C. Cơ chế prefix là **fallback cho liên kết native method**, không phải thay thế `System.loadLibrary`.

### 5.2. JNI `RegisterNatives`

Một thư viện native có thể không dựa vào symbol tìm tự động mà đăng ký ánh xạ bằng `RegisterNatives`, chẳng hạn ý định:

~~~text
method read(long)  ->  nativeFunctionRead
~~~

Sau khi transformer chuyển method native thành `$observe$read`, quy tắc prefix cho phép JVM thử ánh xạ tương ứng với:

~~~text
method $observe$read(long)  ->  nativeFunctionRead
~~~

Đây là sơ đồ ánh xạ, **không phải mã C có thể biên dịch độc lập**. Cơ chế đăng ký vẫn phải khớp kiểu tham số, kiểu trả về, class, loading và quy tắc JNI. Nếu symbol hoặc ánh xạ khác thực tế, `setNativeMethodPrefix` không thể tự tạo ra native implementation bị thiếu.

### 5.3. Nhiều lớp wrapper

Một phương thức `foo` có thể được hai hoặc nhiều transformer bọc lần lượt. Mỗi transformer dùng prefix của mình, chẳng hạn:

~~~text
foo
  -> $trace$foo                 (transformer A)
  -> $metrics$$trace$foo        (transformer B)
~~~

JVM dùng trình tự prefix của các transformer và xem xét sự tồn tại của wrapper trung gian để có thể tìm đúng native implementation. Nếu transformer B bỏ qua một method cụ thể, không nên tự suy ra rằng prefix B vẫn được thêm cho method đó. Đây là lý do tài liệu API yêu cầu **mỗi transformer có prefix riêng**, và khi nhiều agent hoạt động chung phải kiểm thử chain thực tế.

Đặt prefix quá chung như `"wrapped_"` có thể va chạm với method vốn có trong ứng dụng; prefix dài và đặc thù như `"$$$ExampleTraceAgentNative$$$_"` giảm khả năng đó. Quy tắc thử lại chỉ kích hoạt **khi resolution chuẩn thất bại**, nên method không bọc vẫn có thể dùng JNI bình thường.

## 6. Những giới hạn khi đưa tính năng vào một agent thật

Một kiến trúc hoạt động cần đủ **cả hai phần**:

1. `ClassFileTransformer` tạo bytecode hợp lệ và **bọc** native method bằng method Java tương ứng. Trong thực tế thường dùng thư viện xử lý class file phù hợp phiên bản JVM, thay vì thao tác byte thủ công.
2. `setNativeMethodPrefix` giúp native method đã đổi tên được liên kết lại với triển khai JNI gốc qua cơ chế thử lại.

Từ đó phát sinh một số giới hạn:

- **Thời điểm class definition:** bọc native method bằng cách thêm wrapper, đổi tên và sửa modifier là dạng thay đổi cấu trúc method. Nên thiết kế transformer áp dụng **trước khi lớp được định nghĩa lần đầu**. `retransformClasses`/`redefineClasses` với lớp đã nạp có những giới hạn nghiêm ngặt (không được tùy ý thêm/xóa method hay đổi chữ ký/Modifier). Khai báo `Can-Retransform-Classes: true` không loại bỏ các giới hạn đó.
- **Không phải agent nào cũng cần prefix:** nếu công việc chỉ ghi log lúc class load, đo Java methods bình thường hoặc dùng phương án khác không tạo Java wrapper quanh method `native`, không cần yêu cầu capability.
- **JNI thực tế vẫn phải tồn tại:** lớp có thể vẫn gặp `UnsatisfiedLinkError` do thư viện không được load, symbol sai, native signature sai, kiến trúc CPU không khớp, hoặc `RegisterNatives` thất bại. Prefix không chữa các lỗi này.
- **Giữ đúng ngữ nghĩa:** wrapper phải bảo toàn giá trị trả về, exception, `static`/instance invocation, synchronization và thứ tự side-effect. Chú ý overload, native method có signature phức tạp, tên symbol JNI bị mã hóa và các class loader khác nhau.
- **Khởi tạo an toàn:** với `-javaagent`, lỗi chưa xử lý trong `premain` có thể chặn JVM khởi động. Nếu native prefix là chức năng bắt buộc, báo lỗi rõ capability; nếu tùy chọn, có thể tắt riêng chức năng đó trước khi đăng ký transformer và ghi một trạng thái dễ quan sát.
- **Chi phí đo đạc:** wrapper tạo thêm lời gọi Java và xử lý đo đạc; phải đo overhead và không gây recursion khi agent chạm vào các API mà chính nó instrument.
- **Hệ sinh thái nhiều agent:** xác định thứ tự transformer, prefix trùng, sự có mặt của wrapper trung gian và khả năng tương thích giữa các công cụ. Cài được prefix chưa chứng minh chain native call chạy đúng.
- **Cleanup:** `setNativeMethodPrefix(transformer, null)` hoặc `""` tắt quy tắc retry cho transformer; `removeTransformer` bỏ đăng ký callback về sau, song không mặc nhiên phục hồi định nghĩa class đã được sửa. Không giả định thay prefix hoặc remove transformer có thể hoàn tác mọi lớp được transform trước đó.

## 7. Debug theo triệu chứng

| Quan sát | Nguyên nhân có khả năng | Cách kiểm tra |
| --- | --- | --- |
| `isNativeMethodPrefixSupported() == false` | Manifest thiếu/sai `Can-Set-Native-Method-Prefix` hoặc VM không hỗ trợ | Mở **JAR đã deploy**, đọc `META-INF/MANIFEST.MF`, so sánh JDK/JVM triển khai |
| `UnsupportedOperationException` tại `setNativeMethodPrefix` | Cấu hình không cho phép đặt native prefix | Kiểm tra capability **trước lời gọi** và xác nhận đúng agent JAR |
| `IllegalArgumentException` tại `setNativeMethodPrefix` | Instance transformer chưa được đăng ký | Giữ cùng instance, gọi `addTransformer` trước; tránh tạo transformer mới khi set |
| `NullPointerException` khi truyền transformer | Truyền `null` ở tham số đầu | Kiểm tra đối tượng transformer; `null` ở **tham số prefix** có ý nghĩa khác |
| Không thấy wrapper được dùng | Transformer không áp dụng cho class, class đã nạp trước đó, hoặc trả `null`/bytes không thay đổi | Log tên lớp, loader, thời điểm `transform`; kiểm tra class đã transform |
| `UnsatisfiedLinkError` tại native wrapper | Prefix không trùng tên method, thiếu JNI library/symbol, signature sai hoặc resolution vẫn không tìm được | Kiểm tra tên method sau transform, prefix đã đăng ký, native mapping/symbol và load thư viện |
| Có hai hoặc nhiều agent, native linking khác dự kiến | Chain transformer/prefix thay đổi thứ tự hoặc va chạm tên | Ghi lại thứ tự đăng ký, class bytes sau mỗi biến đổi và wrapper trung gian |
| `NoClassDefFoundError`/`ClassFormatError`/`VerifyError` khi load lớp | Transformer sinh bytes lỗi hoặc thiếu dependency | Kiểm thử bytecode đã sinh với JDK thực tế; đọc root cause và định dạng class file |

**Quy trình ngắn để kiểm tra tính năng:** mở manifest thực → gọi `isNativeMethodPrefixSupported()` → ghi nhận transformer instance đã đăng ký → đặt prefix khớp với bytecode sinh ra → xác minh tên method và wrapper sau biến đổi → tải đúng JNI library → chạy bài kiểm thử native thực tế. Không dùng một log "prefix-configured" làm bằng chứng rằng native instrumentation đã thành công.

## 8. Các nhầm lẫn thường gặp

- **"Đặt `Can-Set-Native-Method-Prefix: true` là đủ để biến `native` thành Java method."** Sai. Manifest yêu cầu capability; transformer vẫn phải sinh wrapper.
- **"`isNativeMethodPrefixSupported()` cho biết JVM đã tìm được JNI library."** Sai. Nó chỉ phản ánh khả năng cấu hình native prefix, không kiểm tra thư viện hoặc symbol.
- **"`setNativeMethodPrefix` đổi tên JNI symbol trên đĩa."** Sai. Nó điều chỉnh **quy tắc thử lại khi resolution thất bại**; không biên dịch hay sửa DLL/SO.
- **"Có thể set prefix cho transformer bất kỳ chưa đăng ký."** Sai. Transformer phải được `addTransformer` bằng chính đối tượng đó.
- **"`prefix = null` sẽ gây `NullPointerException`."** Sai: **`null transformer`** mới gây lỗi đó; `null`/rỗng ở **prefix** làm tắt quy tắc retry của transformer.
- **"Mọi native method đều tự được bọc."** Sai. Agent chỉ instrument các lớp/method mà transformer thực sự biến đổi đúng cách.
- **"Có thể thêm method native wrapper sau khi class đã load chỉ bằng `retransformClasses`."** Không thể tùy ý thay đổi cấu trúc lớp khi retransformation; nên tạo wrapper ngay ở initial class definition.
- **"`Can-Set-Native-Method-Prefix`, `Can-Retransform-Classes` và `Can-Redefine-Classes` cùng một cờ."** Sai. Đây là các capability độc lập.
- **"Thí nghiệm API báo `prefix-configured` chứng minh có native method được instrument."** Sai. Demo ở trên cố ý dùng transformer không đổi bytecode; test JNI end-to-end cần thêm native library và một transformer tạo wrapper thật.

## 9. Ghi nhớ và đọc sâu

**Nhớ theo chuỗi điều kiện:**

~~~text
Agent manifest yêu cầu Can-Set-Native-Method-Prefix: true
         +
JVM thực tế có hỗ trợ
         |
         v
isNativeMethodPrefixSupported() == true
         |
         v
addTransformer(transformer)
         |
         v
setNativeMethodPrefix(transformer, "$unique$")
         |
         v
Transformer sinh wrapper Java và đổi tên native method khi class được định nghĩa
         |
         v
Native resolution chuẩn thất bại -> JVM thử lại theo prefix
         |
         v
Nếu có JNI implementation hợp lệ, wrapper Java có thể gọi native logic gốc
~~~

**Tài liệu chính thức:**

- [Java SE 17 — `java.lang.instrument`: Manifest Attributes](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/package-summary.html): `Can-Set-Native-Method-Prefix`, cách nạp agent và ý nghĩa các cờ capability.
- [Java SE 17 — `Instrumentation.isNativeMethodPrefixSupported` và `setNativeMethodPrefix`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): điều kiện hỗ trợ, native resolution, ví dụ wrapper, exception và nhiều transformer.
- [Java SE 17 — `Instrumentation.retransformClasses`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/Instrumentation.html#retransformClasses(java.lang.Class...)): những giới hạn khi instrument lớp đã được định nghĩa.
