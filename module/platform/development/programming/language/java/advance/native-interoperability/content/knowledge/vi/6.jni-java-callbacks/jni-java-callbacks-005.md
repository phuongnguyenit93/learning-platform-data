# Đọc hoặc ghi trường đối tượng và trường static bằng hàm đúng kiểu trong JNI

## Mục tiêu học tập

Khi mã C/C++ gọi ngược vào thế giới Java qua Java Native Interface (JNI), nó không thể đọc hoặc sửa trường Java bằng cách coi đối tượng Java như một cấu trúc C rồi truy cập trực tiếp bộ nhớ. Sau bài này, bạn sẽ:

1. Phân biệt trường **instance** (thuộc từng đối tượng) và trường **static** (thuộc lớp) khi truy cập từ JNI.
2. Xác định đúng **jclass**, **jobject**, **jfieldID** và **field descriptor** trước khi đọc/ghi.
3. Chọn chính xác cặp hàm **Get<Type>Field / Set<Type>Field** hoặc **GetStatic<Type>Field / SetStatic<Type>Field** tương ứng với kiểu Java.
4. Hiểu cách đọc/ghi primitive, String, object và mảng; quản lý local reference do JNI trả về.
5. Xử lý trường hợp tìm sai tên, sai signature, sai static/instance, lớp khởi tạo lỗi hoặc exception đang pending.
6. Chạy ví dụ Java 17+ và C/JNI hoàn chỉnh để thấy thay đổi dữ liệu Java từ native code, rồi áp dụng checklist an toàn cho production.

Phạm vi tập trung vào **truy cập trường Java từ JNI**. Những chủ đề rộng hơn như gọi Java method, quản lý mảng native, pinning hoặc thiết kế toàn bộ vòng đời JNI chỉ được nhắc đến khi chúng ảnh hưởng trực tiếp đến thao tác với field.

## 1. Vì sao JNI cần các hàm truy cập trường?

Giả sử Java định nghĩa:

~~~java
final class SampleState {
    private int count = 7;
    private String name = "initial";

    private static long total = 100L;
    private static String mode = "idle";
}
~~~

Ta có hai loại trường với vòng đời khác nhau:

| Trường Java | Chủ sở hữu logic | Muốn truy cập từ JNI cần |
| --- | --- | --- |
| **count**, kiểu int | Từng đối tượng SampleState | Một **jobject**, field ID kiểu **I**, hàm **GetIntField / SetIntField** |
| **name**, kiểu String | Từng đối tượng SampleState | Một **jobject**, field ID kiểu **Ljava/lang/String;**, hàm **GetObjectField / SetObjectField** |
| **total**, kiểu static long | Lớp SampleState | Một **jclass**, static field ID kiểu **J**, hàm **GetStaticLongField / SetStaticLongField** |
| **mode**, kiểu static String | Lớp SampleState | Một **jclass**, static field ID kiểu **Ljava/lang/String;**, hàm **GetStaticObjectField / SetStaticObjectField** |

Trong Java thuần, compiler và JVM biết type, class, field offset và các quy tắc truy cập. JNI cung cấp một **giao diện ổn định theo ngữ nghĩa**, nên mã native dùng các thao tác có tên rõ ràng thay vì tự suy đoán layout Java object. Layout thực tế có thể thay đổi theo JVM, garbage collector, JIT và cấu hình runtime.

JNI thao tác qua **tham chiếu Java** do JVM quản lý. Một **jobject không phải con trỏ C trực tiếp đến struct** của đối tượng Java; tuyệt đối không ép kiểu rồi dùng phép toán con trỏ để tìm trường.

### Bốn thành phần nền tảng

- **JNIEnv \***: bảng hàm JNI dùng trong thread hiện tại; không chia sẻ con trỏ này giữa các native thread khác nhau.
- **jobject**: tham chiếu đến một đối tượng Java cụ thể; dùng với instance field.
- **jclass**: tham chiếu đến đối tượng Class do JVM quản lý; dùng để tra field ID và truy cập static field.
- **jfieldID**: định danh field do JVM cấp; không phải jobject, không phải Java reference và không được truyền vào DeleteLocalRef.

Một field ID được tra bằng **tên trường + descriptor kiểu + loại instance/static + lớp liên quan**. Sau khi tra thành công, các phép get/set không cần tìm lại tên trường ở mỗi lần truy cập.

## 2. Quy trình chuẩn: tìm lớp → tìm field ID → truy cập đúng họ hàm

Với một đối tượng đã nhận từ Java vào native method:

~~~c
// Ví dụ minh họa bên trong một native method có env và obj hợp lệ.
jclass cls = (*env)->GetObjectClass(env, obj);
if (cls == NULL) {
    return; // Đã có exception tương ứng, ví dụ lỗi cấp phát.
}

jfieldID countId = (*env)->GetFieldID(env, cls, "count", "I");
if (countId == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return; // Không tiếp tục khi lookup thất bại.
}

jint oldCount = (*env)->GetIntField(env, obj, countId);
(*env)->SetIntField(env, obj, countId, oldCount + 1);

(*env)->DeleteLocalRef(env, cls);
~~~

**Đoạn này chỉ là snippet**, không phải file C hoàn chỉnh: nó giả định có sẵn env, obj, một lớp Java mang trường count kiểu int và một native method phù hợp. Ví dụ chạy độc lập xuất hiện tại mục 7.

Quy trình này có ba bước:

1. **GetObjectClass(env, obj)** lấy một **local jclass reference** trỏ đến lớp runtime của đối tượng.
2. **GetFieldID(env, cls, "count", "I")** tìm **instance field** mang tên count với descriptor **I**, trả về jfieldID.
3. **GetIntField / SetIntField** thực hiện truy cập với **jobject obj** và field ID đã tìm.

Đối với **static field**, thay đổi hai điểm: dùng **GetStaticFieldID** để tìm ID, sau đó dùng **GetStaticIntField / SetStaticIntField** (hoặc họ hàm tương ứng) với **jclass**, không truyền jobject ở vị trí đó.

### Bảng đối chiếu instance và static

| Thao tác | Instance field | Static field |
| --- | --- | --- |
| Tìm ID | **GetFieldID(env, cls, name, sig)** | **GetStaticFieldID(env, cls, name, sig)** |
| Đọc int | **GetIntField(env, obj, id)** | **GetStaticIntField(env, cls, id)** |
| Ghi int | **SetIntField(env, obj, id, value)** | **SetStaticIntField(env, cls, id, value)** |
| Đọc String hoặc object | **GetObjectField(env, obj, id)** | **GetStaticObjectField(env, cls, id)** |
| Ghi String hoặc object | **SetObjectField(env, obj, id, ref)** | **SetStaticObjectField(env, cls, id, ref)** |
| Đối số nơi lưu dữ liệu | **jobject** chứa giá trị từng instance | **jclass** đại diện lớp khai báo/truy cập static |

Tên hàm có chữ **Static** là dấu hiệu bắt buộc. Không lấy ID của một static field bằng GetFieldID, không dùng SetIntField để ghi một static int, và không tráo một jfieldID static sang họ instance hay ngược lại.

## 3. Field descriptor: mô tả kiểu, không mô tả phương thức

**Descriptor** là chuỗi ký hiệu kiểu dùng bởi JVM/JNI. Field lookup yêu cầu descriptor khớp **kiểu khai báo của field**, không phải kiểu giá trị bạn muốn ép sang hoặc kiểu C của biến nhận kết quả.

| Kiểu khai báo Java | Field descriptor | Kiểu JNI / họ hàm truy cập |
| --- | --- | --- |
| boolean | **Z** | **jboolean**, Boolean |
| byte | **B** | **jbyte**, Byte |
| char | **C** | **jchar**, Char |
| short | **S** | **jshort**, Short |
| int | **I** | **jint**, Int |
| long | **J** | **jlong**, Long |
| float | **F** | **jfloat**, Float |
| double | **D** | **jdouble**, Double |
| java.lang.String | **Ljava/lang/String;** | **jobject/jstring**, Object |
| java.util.List | **Ljava/util/List;** | **jobject**, Object |
| int[] | **[I** | **jobject/jintArray**, Object |
| String[] | **[Ljava/lang/String;** | **jobject/jobjectArray**, Object |
| int[][] | **[[I** | **jobject** (có thể dùng kiểu tham chiếu mảng phù hợp), Object |

Đối với reference type, descriptor bắt đầu bằng **L**, dùng tên lớp với dấu **/** thay vì dấu **.**, và kết thúc bằng **;**. Mảng dùng một dấu **[** cho mỗi chiều. Kiểu field không có dấu ngoặc tròn; chuỗi như **(I)V** là **method descriptor**, không thể dùng để tìm field int.

Ví dụ lookup:

~~~c
jfieldID pointsId =
    (*env)->GetFieldID(env, cls, "points", "I");

jfieldID titleId =
    (*env)->GetFieldID(env, cls, "title", "Ljava/lang/String;");

jfieldID valuesId =
    (*env)->GetFieldID(env, cls, "values", "[I");

jfieldID objectsId =
    (*env)->GetStaticFieldID(env, cls, "objects", "[Ljava/lang/Object;");
~~~

Đây là đoạn minh họa độc lập về **chuỗi descriptor**; nó yêu cầu các trường tương ứng thực sự tồn tại trong lớp. Các lời gọi lookup phải được **kiểm tra lỗi trước khi sử dụng ID**, như ở ví dụ đầy đủ.

### Cách tránh đoán nhầm descriptor

Với lớp đã biên dịch, lệnh **javap -s -private TenLop** hiển thị tên và descriptor của field:

~~~bash
javac SampleState.java
javap -s -private SampleState
~~~

Lệnh **-private** giúp nhìn thấy cả trường private; **-s** hiển thị descriptor. Có thể dùng **javap -s** như bằng chứng trực tiếp khi Java source thay đổi hoặc descriptor của kiểu lồng nhau phức tạp. Không tự đoán chữ hoa/chữ thường: **I khác J**, **L khác [**, và **Ljava/lang/String;** phải có dấu chấm phẩy cuối.

## 4. Đọc/ghi primitive bằng hàm đúng kiểu

JNI có các họ hàm cụ thể theo từng primitive. Tên ký hiệu **<Type>** trong tài liệu đại diện cho một trong những hậu tố bên dưới; trong C code thật phải dùng **tên hàm đầy đủ**.

| Java type | Đọc instance | Ghi instance | Đọc static | Ghi static |
| --- | --- | --- | --- | --- |
| boolean | GetBooleanField | SetBooleanField | GetStaticBooleanField | SetStaticBooleanField |
| byte | GetByteField | SetByteField | GetStaticByteField | SetStaticByteField |
| char | GetCharField | SetCharField | GetStaticCharField | SetStaticCharField |
| short | GetShortField | SetShortField | GetStaticShortField | SetStaticShortField |
| int | GetIntField | SetIntField | GetStaticIntField | SetStaticIntField |
| long | GetLongField | SetLongField | GetStaticLongField | SetStaticLongField |
| float | GetFloatField | SetFloatField | GetStaticFloatField | SetStaticFloatField |
| double | GetDoubleField | SetDoubleField | GetStaticDoubleField | SetStaticDoubleField |

Ví dụ nếu Java có **private boolean enabled** và **private static double factor**:

~~~c
jfieldID enabledId =
    (*env)->GetFieldID(env, cls, "enabled", "Z");
if (enabledId == NULL) {
    return;
}

jboolean enabled = (*env)->GetBooleanField(env, obj, enabledId);
(*env)->SetBooleanField(
    env, obj, enabledId, enabled == JNI_TRUE ? JNI_FALSE : JNI_TRUE
);

jfieldID factorId =
    (*env)->GetStaticFieldID(env, cls, "factor", "D");
if (factorId == NULL) {
    return;
}

jdouble factor = (*env)->GetStaticDoubleField(env, cls, factorId);
(*env)->SetStaticDoubleField(env, cls, factorId, factor * 2.0);
~~~

Đây là **snippet minh họa**, giả sử env, obj, cls hợp lệ và các field tồn tại; production phải dọn local references và xử lý exception theo bối cảnh. Trong code này:

- **enabled** có descriptor **Z**, nên sử dụng **GetBooleanField / SetBooleanField** và kiểu **jboolean**.
- **factor** có descriptor **D**, là trường **static double**, nên dùng **GetStaticDoubleField / SetStaticDoubleField** và kiểu **jdouble**.
- Giá trị boolean JNI nên dùng **JNI_TRUE** và **JNI_FALSE** thay vì suy luận từ cách compiler C biểu diễn boolean.
- **jchar** là mã đơn vị UTF-16 16 bit; không đồng nhất với **char** 8 bit của C.
- **jlong** là kiểu JNI cho Java long 64 bit; không mặc định rằng **long** trong C luôn dài 64 bit (Windows có mô hình ABI khác nhiều Unix).
- Không đọc trường **int** bằng **GetLongField** rồi kỳ vọng JNI tự nới kiểu. Với field descriptor **I**, phải dùng **GetIntField**; nếu cần long, thực hiện chuyển kiểu có chủ đích ở C sau khi nhận **jint**.

### Ví dụ sai nghiêm trọng

~~~c
jfieldID id = (*env)->GetFieldID(env, cls, "score", "I");

// Sai: score khai báo int nhưng lại dùng getter double.
jdouble wrong = (*env)->GetDoubleField(env, obj, id);
~~~

Mã này cố ý sai và **không được chạy trong ứng dụng thực**. JNI có các điều kiện hợp đồng về loại field ID và kiểu accessor; vi phạm có thể gây lỗi nghiêm trọng, crash hoặc hành vi không dự đoán được. Khi bật **-Xcheck:jni** trên JVM hỗ trợ, nhiều cách dùng sai sẽ được phát hiện sớm, nhưng chế độ kiểm tra không thay thế thiết kế đúng.

## 5. Đọc/ghi String, object và mảng: dùng họ Object

Field có kiểu **reference** không sử dụng một getter riêng tên String/Array/List. Thay vào đó, JNI cung cấp:

- **GetObjectField(env, obj, id)** và **SetObjectField(env, obj, id, value)** cho instance reference field.
- **GetStaticObjectField(env, cls, id)** và **SetStaticObjectField(env, cls, id, value)** cho static reference field.

Trong mã C, kết quả đọc mang kiểu **jobject**. Với đúng kiểu được khai báo, có thể ép sang **jstring**, **jintArray** hoặc một loại JNI reference tương ứng để sử dụng API chuyên biệt. Thao tác ép kiểu C **không đổi kiểu thực của Java object**, nên phải tuân thủ descriptor và hợp đồng của trường.

Ví dụ Java:

~~~java
final class ReferenceHolder {
    private String title = "old";
    private int[] scores = {3, 4};
    private static String status = "idle";
}
~~~

Các lời gọi JNI tương ứng:

~~~c
// Đoạn minh họa: giả sử env, obj, cls hợp lệ;
// tất cả lookup cần được kiểm tra thành công trước khi dùng.
jfieldID titleId =
    (*env)->GetFieldID(env, cls, "title", "Ljava/lang/String;");
jfieldID scoresId =
    (*env)->GetFieldID(env, cls, "scores", "[I");
jfieldID statusId =
    (*env)->GetStaticFieldID(env, cls, "status", "Ljava/lang/String;");

jstring title = (jstring)(*env)->GetObjectField(env, obj, titleId);
jintArray scores = (jintArray)(*env)->GetObjectField(env, obj, scoresId);
jstring status = (jstring)(*env)->GetStaticObjectField(env, cls, statusId);

// Khi không dùng nữa:
if (title != NULL) (*env)->DeleteLocalRef(env, title);
if (scores != NULL) (*env)->DeleteLocalRef(env, scores);
if (status != NULL) (*env)->DeleteLocalRef(env, status);
~~~

**Lưu ý:** đoạn trên được rút gọn để minh họa đúng loại getter; phải kiểm tra **titleId/scoresId/statusId != NULL** trước mỗi lần gọi getter, và không gọi thêm JNI API thông thường khi có pending exception. Ví dụ đầy đủ ở mục 7 thể hiện luồng kiểm soát này.

### Local reference khác với giá trị của field

**GetObjectField** và **GetStaticObjectField** trả về **local reference** của JNI đối với Java object đang được lưu trong field (hoặc NULL nếu Java field là null). Local reference do JNI trả về thường chỉ có hiệu lực trong native call hiện tại, và các native call dài/vòng lặp tạo nhiều reference cần **DeleteLocalRef** hoặc local frame để tránh tích lũy.

Ngược lại, khi tạo chuỗi mới:

~~~c
jstring text = (*env)->NewStringUTF(env, "updated");
if (text == NULL) {
    return; // Có thể đang pending OutOfMemoryError.
}
(*env)->SetObjectField(env, obj, titleId, text);
(*env)->DeleteLocalRef(env, text);
~~~

Lệnh **DeleteLocalRef(text)** chỉ bỏ **tham chiếu cục bộ ở JNI**. Sau khi gán thành công, trường Java vẫn giữ reference của nó tới String; đối tượng không biến mất chỉ vì local reference đã được xóa. Không được dùng **free(text)** vì **jstring không phải con trỏ malloc**.

**NewStringUTF** nhận modified UTF-8 theo hợp đồng JNI; nếu dữ liệu nguồn là chuỗi UTF-8 bất kỳ từ I/O (đặc biệt có byte null hoặc các chuỗi encoding không hợp lệ), cần chuyển đổi đúng quy tắc thay vì giả định mọi byte buffer đều là modified UTF-8. Ví dụ ở mục 7 chỉ dùng văn bản ASCII nên không gặp sự khác biệt này.

### Mảng là object field, nhưng chiều dài không phải field có thể lookup

Nếu Java khai báo **int[] scores**, dùng **GetObjectField** với descriptor **[I** để nhận tham chiếu mảng. Sau đó có thể gọi **GetArrayLength(env, scores)** để lấy độ dài; không dùng **GetFieldID(..., "length", "I")** trên kiểu mảng. Việc đọc phần tử cần dùng API mảng của JNI (ví dụ GetIntArrayRegion), nằm ngoài phạm vi truy cập field của bài này.

## 6. Static field có điểm khác biệt quan trọng nào?

Mỗi runtime class có trạng thái static riêng theo định danh lớp/class loader. Khi đọc/ghi static field từ JNI:

1. Lấy **jclass** đại diện cho lớp liên quan.
2. Gọi **GetStaticFieldID** với tên và descriptor đúng.
3. Dùng **GetStatic<Type>Field / SetStatic<Type>Field** cùng **jclass** và ID tương ứng.
4. Dọn **jclass local reference** nếu không cần nữa.

Ví dụ cho Java **static int nextId = 20**:

~~~c
jfieldID id =
    (*env)->GetStaticFieldID(env, cls, "nextId", "I");
if (id == NULL) {
    return; // Có thể đang pending NoSuchFieldError.
}

jint current = (*env)->GetStaticIntField(env, cls, id);
(*env)->SetStaticIntField(env, cls, id, current + 1);
~~~

Không có đối số **jobject** trong hai hàm static ở đây. Cũng không dùng **GetFieldID** vì nextId là static.

### Lookup field ID có thể kích hoạt khởi tạo lớp

Theo JNI Specification, cả **GetFieldID** và **GetStaticFieldID** đều có thể kích hoạt **class initialization** nếu lớp chưa được khởi tạo. Điều này có thể thực thi khối static Java, kéo theo nạp thư viện, I/O hoặc exception khởi tạo.

Nếu lookup thất bại, bạn có thể gặp **NoSuchFieldError** (không tìm được đúng field) hoặc **ExceptionInInitializerError** nếu khởi tạo lớp phát sinh exception tương ứng, cùng một số lỗi tài nguyên. Đừng cho rằng GetFieldID/GetStaticFieldID chỉ tra metadata và hoàn toàn không có tác dụng phụ.

Trong ví dụ thực hành, native method được gọi **sau khi lớp Java đã khởi tạo** nên việc tra field không gây một vòng khởi tạo bổ sung.

### Cảnh báo với static final

Không dùng JNI để thay đổi giá trị của một **final field**, đặc biệt **static final constant**, như một cơ chế cấu hình. Tài liệu JNI hiện hành cảnh báo rằng dù có thể truyền field ID của final field vào setter, kết quả có thể gây exception không mong muốn hoặc crash. Java compiler/JIT cũng có thể tối ưu hoặc nội tuyến giá trị constant khiến các nơi đọc quan sát không nhất quán.

Quy tắc tốt: xem **final** là bất biến theo hợp đồng; đặt cấu hình cần thay đổi vào API Java có setter được kiểm soát, cấu trúc dữ liệu bất biến được thay thế có chủ đích, hoặc cơ chế state quản lý tương ứng.

## 7. Thực hành hoàn chỉnh: Java 17+ kết hợp C/JNI

Ví dụ dưới đây đọc và ghi **bốn trường** của cùng một lớp:

- **count**: instance int → GetIntField / SetIntField.
- **label**: instance String → GetObjectField / SetObjectField.
- **total**: static long → GetStaticLongField / SetStaticLongField.
- **mode**: static String → GetStaticObjectField / SetStaticObjectField.

Code Java in ra giá trị trước/sau; mã C truy cập các field qua đúng ID và đúng họ accessor.

### Bước 1 — Tạo file FieldAccessDemo.java

~~~java
public final class FieldAccessDemo {
    private int count = 7;
    private String label = "initial";

    private static long total = 100L;
    private static String mode = "idle";

    static {
        System.loadLibrary("fieldaccessdemo");
    }

    private native void mutate();

    public static void main(String[] args) {
        FieldAccessDemo data = new FieldAccessDemo();

        System.out.printf(
            "before: count=%d, label=%s, total=%d, mode=%s%n",
            data.count, data.label, total, mode
        );

        data.mutate();

        System.out.printf(
            "after: count=%d, label=%s, total=%d, mode=%s%n",
            data.count, data.label, total, mode
        );
    }
}
~~~

Đây là **chương trình Java hoàn chỉnh** nhưng phải có thư viện native biên dịch từ C ở bước tiếp theo để chạy thành công. **mutate** là phương thức native instance, vì thế JNI entry point nhận **JNIEnv \*** và **jobject self**. Trong main, lần active use của lớp kích hoạt static initializer, gọi System.loadLibrary; nếu không tìm thấy library, ứng dụng báo UnsatisfiedLinkError và không đi tiếp vào thao tác field.

### Bước 2 — Biên dịch Java và sinh JNI header

Trong thư mục chứa file Java:

~~~bash
javac -h . FieldAccessDemo.java
~~~

Lệnh tạo ít nhất **FieldAccessDemo.class** và **FieldAccessDemo.h**. Hãy dùng header do **javac -h** sinh, không tự suy đoán cách JNI mã hóa tên hàm. Với lớp không thuộc package và native method như ở trên, phần khai báo tương ứng có tên **Java_FieldAccessDemo_mutate**.

### Bước 3 — Tạo file field_access_demo.c

~~~c
#include "FieldAccessDemo.h"

/*
 * Generated header xác định tên và chữ ký JNI.
 * self là jobject của instance gọi mutate().
 */
JNIEXPORT void JNICALL
Java_FieldAccessDemo_mutate(JNIEnv *env, jobject self) {
    jclass cls = NULL;
    jfieldID countId = NULL;
    jfieldID labelId = NULL;
    jfieldID totalId = NULL;
    jfieldID modeId = NULL;

    jobject oldLabel = NULL;
    jobject oldMode = NULL;
    jstring nextLabel = NULL;
    jstring nextMode = NULL;

    jint oldCount = 0;
    jlong oldTotal = 0;

    /* Lấy class runtime của self (FieldAccessDemo là final). */
    cls = (*env)->GetObjectClass(env, self);
    if (cls == NULL) {
        return; /* JVM đã phát sinh exception tương ứng. */
    }

    /* Tra ID: instance field dùng GetFieldID. */
    countId = (*env)->GetFieldID(env, cls, "count", "I");
    if (countId == NULL) goto cleanup;

    labelId = (*env)->GetFieldID(
        env, cls, "label", "Ljava/lang/String;"
    );
    if (labelId == NULL) goto cleanup;

    /* Tra ID: static field dùng GetStaticFieldID. */
    totalId = (*env)->GetStaticFieldID(env, cls, "total", "J");
    if (totalId == NULL) goto cleanup;

    modeId = (*env)->GetStaticFieldID(
        env, cls, "mode", "Ljava/lang/String;"
    );
    if (modeId == NULL) goto cleanup;

    /* Đọc primitive bằng đúng họ kiểu và đúng loại field. */
    oldCount = (*env)->GetIntField(env, self, countId);
    oldTotal = (*env)->GetStaticLongField(env, cls, totalId);

    /* Đọc reference field: kết quả là local reference hoặc NULL. */
    oldLabel = (*env)->GetObjectField(env, self, labelId);
    if ((*env)->ExceptionCheck(env)) goto cleanup;

    oldMode = (*env)->GetStaticObjectField(env, cls, modeId);
    if ((*env)->ExceptionCheck(env)) goto cleanup;

    /* Chuẩn bị đủ object cần ghi trước khi thay đổi state. */
    nextLabel = (*env)->NewStringUTF(env, "from JNI");
    if (nextLabel == NULL) goto cleanup;

    nextMode = (*env)->NewStringUTF(env, "native");
    if (nextMode == NULL) goto cleanup;

    /* Ghi primitive và reference bằng đúng accessor. */
    (*env)->SetIntField(env, self, countId, oldCount + 5);
    (*env)->SetObjectField(env, self, labelId, nextLabel);

    (*env)->SetStaticLongField(env, cls, totalId, oldTotal + 25);
    (*env)->SetStaticObjectField(env, cls, modeId, nextMode);

cleanup:
    /*
     * DeleteLocalRef là thao tác dọn local reference,
     * được dùng được khi còn pending Java exception.
     * Nếu tra field / tạo string lỗi, exception gốc tiếp tục
     * truyền về Java khi native method trả về.
     */
    if (nextMode != NULL) (*env)->DeleteLocalRef(env, nextMode);
    if (nextLabel != NULL) (*env)->DeleteLocalRef(env, nextLabel);
    if (oldMode != NULL) (*env)->DeleteLocalRef(env, oldMode);
    if (oldLabel != NULL) (*env)->DeleteLocalRef(env, oldLabel);
    (*env)->DeleteLocalRef(env, cls);
}
~~~

### Tại sao C code được tổ chức như vậy?

1. **GetObjectClass(self)** tạo local jclass reference. Vì Java class là final, class của self là FieldAccessDemo; không có ambiguity do subclass.
2. Hai lệnh **GetFieldID** xác định field instance count và label; hai lệnh **GetStaticFieldID** xác định total và mode. Descriptor **I/J/Ljava/lang/String;** khớp khai báo Java.
3. Mọi lookup đều được kiểm tra **NULL**. Khi lookup thất bại, JNI thường đã đặt một pending exception (ví dụ NoSuchFieldError). Nhánh **cleanup** dọn reference và trở về Java, không thực hiện tiếp getter/setter trên ID sai.
4. **GetIntField** trả **jint**; **GetStaticLongField** trả **jlong**. Không dùng kiểu C long để giả định độ rộng Java long.
5. **GetObjectField** và **GetStaticObjectField** trả local reference. Code không cần sử dụng nội dung chuỗi cũ nhưng cố ý thực hiện cả hai thao tác đọc để minh họa API và vòng đời reference.
6. Hai lệnh **NewStringUTF** chuẩn bị giá trị mới trước khi cập nhật field. Nếu không đủ bộ nhớ, JNI có thể đặt OutOfMemoryError; code không thực hiện các lệnh ghi sau khi tạo string thất bại.
7. Bốn setter chọn đúng loại: **SetIntField**, **SetObjectField**, **SetStaticLongField**, **SetStaticObjectField**. **SetObjectField** nhận một **jstring** hợp lệ, vốn là Java reference tương thích với trường String.
8. **DeleteLocalRef** không xóa giá trị đã lưu trong Java field. Reference mới vẫn do field của đối tượng/lớp giữ sau khi native method kết thúc.

**Giới hạn giao dịch:** ví dụ minh họa thao tác có thứ tự, không phải một transaction. Nếu yêu cầu cập nhật nhiều field có tính nguyên tử giữa các thread hoặc rollback khi lỗi, hãy thiết kế API Java đồng bộ, tạo đối tượng state bất biến rồi thay thế, hoặc dùng cơ chế transaction phù hợp. Bốn lệnh setter độc lập không có nghĩa thay đổi cả bốn là atomic.

### Bước 4 — Build thư viện native

Cài JDK với **JAVA_HOME** trỏ đến thư mục JDK chứa **include/jni.h**, cùng C compiler phù hợp với nền tảng đang chạy. Dùng cùng kiến trúc CPU/ABI với JVM.

**Linux (GCC):**

~~~bash
gcc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  field_access_demo.c -o libfieldaccessdemo.so
~~~

**macOS (Clang):**

~~~bash
clang -std=c11 -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  field_access_demo.c -o libfieldaccessdemo.dylib
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" field_access_demo.c /link /OUT:fieldaccessdemo.dll
~~~

Tên output đúng với cách **System.loadLibrary("fieldaccessdemo")** ánh xạ tên logic trên các nền tảng thông dụng. Lệnh Windows giả định môi trường MSVC đã được khởi tạo; lệnh Linux/macOS giả định GCC/Clang và header tương ứng đã sẵn sàng.

### Bước 5 — Chạy ví dụ

Từ thư mục chứa **FieldAccessDemo.class** và thư viện vừa build:

~~~bash
java -Djava.library.path=. FieldAccessDemo
~~~

**Stdout chính xác trên cấu hình thành công:**

~~~text
before: count=7, label=initial, total=100, mode=idle
after: count=12, label=from JNI, total=125, mode=native
~~~

Nếu dùng JDK có hạn chế native access, chạy trên classpath có thể cần cho phép module unnamed:

~~~bash
java --enable-native-access=ALL-UNNAMED -Djava.library.path=. FieldAccessDemo
~~~

Tùy JDK, gọi System.loadLibrary khi chưa khai báo quyền có thể phát cảnh báo ra **stderr** hoặc bị từ chối theo chính sách. Cảnh báo stderr không phải một phần của stdout mẫu bên trên. Khi chạy trên module path, ưu tiên khai báo quyền cho **module cụ thể** thay vì ALL-UNNAMED.

**Nếu chương trình báo UnsatisfiedLinkError**, hãy kiểm tra tên thư viện, build artifact, JAVA_HOME, JVM architecture, dependency native và java.library.path. Đây là lỗi nạp/liên kết thư viện, không chứng minh các field descriptor sai. Khi thư viện load được nhưng dùng field lookup sai, có thể nhận **NoSuchFieldError**.

### Dùng -Xcheck:jni để phát hiện sai hợp đồng sớm

Trên HotSpot/JVM hỗ trợ:

~~~bash
java -Xcheck:jni -Djava.library.path=. FieldAccessDemo
~~~

Tùy chính sách native access của JDK, kết hợp tùy chọn cho phép native access nếu cần. **-Xcheck:jni** hỗ trợ phát hiện nhiều cách sử dụng JNI bất hợp lệ như truyền field ID sai loại hoặc reference đã vô hiệu. Nó là công cụ chẩn đoán và kiểm thử; không đảm bảo JNI hay thư viện C/C++ hoàn toàn memory-safe.

## 8. Xử lý lỗi của field lookup và pending exception

Hàm **GetFieldID / GetStaticFieldID** trả về **NULL** khi lookup thất bại. Nguyên nhân phổ biến gồm:

| Nguyên nhân | Ví dụ | Hậu quả thường gặp |
| --- | --- | --- |
| Sai tên | Java khai báo **count** nhưng C tìm **counts** | **NoSuchFieldError** |
| Sai descriptor | Java khai báo **long total** nhưng C dùng **"I"** | **NoSuchFieldError** |
| Sai instance/static | Java khai báo **static int level**, C gọi GetFieldID | **NoSuchFieldError** |
| Class initialization thất bại | Static initializer của lớp ném lỗi | Có thể xuất hiện **ExceptionInInitializerError** hoặc lỗi khởi tạo khác |
| Thiếu bộ nhớ | JVM không thể hoàn tất thao tác liên quan | Có thể xuất hiện **OutOfMemoryError** |
| ID đã hết hiệu lực | Tái sử dụng field ID sau khi defining class bị unload | Vi phạm hợp đồng JNI, có thể gây lỗi nghiêm trọng |

Hãy kiểm tra **NULL** ngay sau lookup:

~~~c
jfieldID id = (*env)->GetFieldID(env, cls, "count", "I");
if (id == NULL) {
    // Đang có pending exception; dọn local references cần thiết,
    // rồi return để Java xử lý lỗi gốc.
    return;
}
~~~

Nếu cần kiểm tra một API có thể đặt exception mà không báo lỗi bằng NULL, dùng **ExceptionCheck**:

~~~c
if ((*env)->ExceptionCheck(env)) {
    // Chỉ gọi các JNI API được phép khi exception đang pending,
    // ví dụ DeleteLocalRef để dọn tài nguyên.
    return;
}
~~~

**Không tiếp tục gọi hàng loạt JNI API thông thường khi có pending exception.** Theo JNI, sau lỗi phải xử lý exception hoặc trả quyền điều khiển cho Java; chỉ một nhóm API được phép sử dụng khi exception vẫn pending. Dọn local reference là một trong những thao tác được phép.

### ExceptionClear không phải “sửa lỗi”

**ExceptionClear** làm mất trạng thái pending exception. Chỉ gọi khi có lý do được thiết kế rõ ràng: chuyển đổi sang exception khác, fallback hợp lệ, hoặc đã xử lý lỗi hoàn toàn. Nếu xóa **NoSuchFieldError** rồi tiếp tục truy cập bằng jfieldID NULL, bạn không giải quyết nguyên nhân và có thể gây crash.

### Không bỏ qua bất biến Java

JNI có thể truy cập field private thông qua field ID, nhưng điều đó không làm việc **bỏ qua setter/validation** trở nên an toàn. Nếu field có ràng buộc nghiệp vụ như “số dư không âm” hoặc “đổi trạng thái phải phát event”, ghi trực tiếp từ C có thể vi phạm invariants mà Java setter thường bảo vệ. Khi hành vi nghiệp vụ quan trọng, cân nhắc gọi phương thức Java công khai bằng JNI thay vì viết trực tiếp vào field.

## 9. Vòng đời của jfieldID, jclass và jobject

Ba loại giá trị dễ bị nhầm:

| Giá trị | Có phải Java reference? | Có dùng DeleteLocalRef? | Có thể cache lâu dài? |
| --- | --- | --- | --- |
| **jobject** local | Có | Có, khi không cần nữa | **Không**, phải tạo global reference nếu cần dùng sau native call |
| **jclass** local | Có | Có | **Không** dưới dạng local reference; dùng NewGlobalRef nếu cần giữ |
| **jfieldID** | **Không** | **Không** | Có thể cache **khi class còn tồn tại**; ID mất hiệu lực nếu class bị unload |

Trong một native method ngắn, lookup ID rồi dùng trực tiếp thường đủ rõ ràng. Nếu field được truy cập nhiều lần và lookup là chi phí đáng kể, cache **jfieldID** hợp lý, nhưng phải quản lý **class loader lifecycle**.

Một cache dùng trên vòng đời dài cần tránh hai vấn đề:

1. **Class unload:** field ID có thể mất hiệu lực khi defining class bị unload; cache không được sử dụng sau thời điểm đó. Có thể giữ global jclass reference để giữ class còn sống khi ứng dụng thật sự cần.
2. **Rò rỉ class loader:** giữ global jclass reference vĩnh viễn có thể ngăn giải phóng class loader trong môi trường plugin/hot reload. Khi module dỡ bỏ, cần dọn global reference và cache đúng lifecycle.

Đừng coi **jfieldID** là địa chỉ offset trường có thể cộng trừ. Đó là một token không minh bạch, chỉ dùng với hàm JNI phù hợp.

## 10. Thread safety và nhất quán dữ liệu

**Đọc/ghi đúng kiểu JNI** chỉ giải quyết **hợp đồng type và instance/static**, chưa đủ để bảo đảm tính đúng trong môi trường đa luồng.

Ví dụ C:

~~~c
jint oldValue = (*env)->GetIntField(env, obj, countId);
(*env)->SetIntField(env, obj, countId, oldValue + 1);
~~~

Đây là thao tác **read-modify-write gồm hai bước**, không phải phép cộng nguyên tử. Nếu hai thread đồng thời thực hiện, cả hai có thể đọc cùng giá trị cũ rồi ghi cùng giá trị mới, dẫn đến **lost update**.

Để thiết kế đúng:

- Xác định rõ field nào được chia sẻ, cả khi Java và native cùng truy cập.
- Dùng đồng bộ hóa phù hợp với Java Memory Model, hoặc chuyển thao tác phức tạp sang một Java method đã có lock/atomic class.
- Với state liên quan nhiều field, tránh cho luồng khác nhìn thấy trạng thái cập nhật dở dang.
- Không suy luận “đã gọi JNI setter thì thread-safe” hoặc “field primitive thì mọi thao tác liên quan đều atomic”.
- Nếu native library tự sinh thread và muốn tương tác JVM, thread đó phải được attach vào JVM và dùng **JNIEnv của chính nó**; không truyền JNIEnv từ thread khác.
- Đừng giữ **local jobject reference** qua native method hoặc trao nó sang thread khác. Khi cần lưu lâu, cân nhắc global reference và giải phóng đúng lifecycle.

Cần phân biệt tính **đúng kiểu** với tính **đúng đồng bộ** và **đúng hợp đồng nghiệp vụ**. Cả ba đều phải thỏa mãn nếu native code sửa state được Java quan sát.

## 11. Những sai lầm điển hình cần tránh

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Dùng **GetFieldID** cho field static | Tra sai loại field | Dùng **GetStaticFieldID**, tiếp đó accessor có chữ Static |
| Dùng **GetStaticIntField** cho field long | Sai họ kiểu, descriptor khác | **GetStaticLongField**, descriptor **J** |
| Đọc int bằng **GetDoubleField** | JNI không tự ép kiểu qua accessor | Dùng **GetIntField** rồi chuyển đổi jint nếu cần |
| Truyền **jobject** thay **jclass** vào static accessor | Sai tham số của JNI API | Lấy/lưu jclass reference phù hợp |
| Truyền **jclass** thay **jobject** vào instance accessor | Lớp không phải instance chứa field | Truyền đối tượng Java cụ thể |
| Truyền descriptor **"java.lang.String"** | Không phải JVM field descriptor | **"Ljava/lang/String;"** |
| Quên dấu **;** hoặc dùng dấu **.** trong reference descriptor | Lookup không tìm thấy field | Dùng tên JVM với **/** và **;** |
| Tiếp tục get/set khi field ID bằng NULL | Exception pending, ID bất hợp lệ | Kiểm tra lỗi, dọn reference, return |
| Dùng **free(jstring)** | jstring là Java reference | Dùng **DeleteLocalRef** cho local reference khi thích hợp |
| Đóng local reference ngay rồi tiếp tục dùng handle | Handle không còn hợp lệ | Dùng trước khi xóa; giữ global ref nếu cần lâu dài |
| Dùng **SetObjectField** với tham chiếu khác kiểu field | Vi phạm hợp đồng kiểu Java | Đối chiếu descriptor và đối tượng thực |
| Cố sửa **static final** bằng JNI | Vi phạm thiết kế bất biến, có rủi ro JIT | Không sửa final; dùng API thiết kế cho cập nhật |
| Giữ **jfieldID** sau khi class unload | ID không còn hiệu lực | Gắn cache vào lifecycle của class/class loader |
| Ghi trực tiếp field private để né validation | Phá vỡ invariant nghiệp vụ | Gọi Java method thích hợp nếu cần bảo vệ state |
| Dùng GetFieldID để tìm **array.length** | length của mảng không được tra bằng ID | Dùng **GetArrayLength** |
| Xem một cặp Get/Set là tăng nguyên tử | Read-modify-write không atomic | Dùng đồng bộ hóa/atomic operation phù hợp |

## 12. Checklist khi review mã JNI truy cập field

- [ ] Xác định field là **instance** hay **static** theo đúng khai báo Java.
- [ ] Lấy **jobject** hoặc **jclass** hợp lệ; không nhầm class của hai class loader khác nhau.
- [ ] Tra field bằng đúng **name**, **descriptor** và **GetFieldID / GetStaticFieldID**.
- [ ] Kiểm tra mỗi lookup trả về **jfieldID khác NULL**, không chạy tiếp với pending exception.
- [ ] Chọn chính xác **Get<Type>Field / Set<Type>Field** hoặc biến thể **Static**.
- [ ] Dùng đúng kiểu JNI (**jint**, **jlong**, **jboolean**, **jobject**...), không giả định kích thước kiểu C tương đương.
- [ ] Với object/reference field, quản lý local/global reference; không free con trỏ JNI hoặc giữ local reference sau vòng đời.
- [ ] Không ghi trực tiếp **final field**, không bỏ qua invariant/validation nghiệp vụ.
- [ ] Nếu nhiều thread truy cập, có chiến lược visibility, đồng bộ hóa và atomicity rõ ràng.
- [ ] Nếu cache **jfieldID/jclass**, xử lý class loader unloading và global reference cleanup.
- [ ] Có test cho field đúng kiểu, sai tên/descriptor, lỗi khởi tạo, pending exception và concurrency.
- [ ] Chạy **-Xcheck:jni** trong test thích hợp; smoke test với chính binary, JVM và ABI sẽ dùng khi triển khai.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Java có **static long total**. Từ JNI phải tra và ghi như thế nào?

**Đáp án:** Dùng **GetStaticFieldID(env, cls, "total", "J")**; nếu ID khác NULL, dùng **SetStaticLongField(env, cls, id, jlongValue)**. Không dùng GetFieldID hoặc SetLongField của instance.

**Câu 2.** Java khai báo **private String label**. Vì sao dùng GetObjectField thay vì GetStringField?

**Đáp án:** String là reference type. JNI dùng họ **ObjectField** cho mọi trường tham chiếu, không có họ GetStringField dành riêng cho trường String. Descriptor của label là **Ljava/lang/String;**.

**Câu 3.** Đọc trường **int[] data** bằng GetObjectField rồi muốn biết độ dài. Có thể dùng GetFieldID với tên **length**?

**Đáp án:** Không. Mảng Java được lấy bằng GetObjectField với descriptor **[I**; dùng **GetArrayLength** trên tham chiếu mảng hợp lệ để lấy kích thước.

**Câu 4.** Vì sao không thể chuyển **jfieldID** qua DeleteLocalRef?

**Đáp án:** jfieldID là định danh metadata không phải Java object reference. DeleteLocalRef chỉ dành cho JNI local references như jobject/jclass/jstring.

**Câu 5.** Hai thread cùng gọi GetIntField rồi SetIntField(value + 1). Có luôn tăng được hai đơn vị không?

**Đáp án:** Không. Đây là read-modify-write nhiều bước, có thể lost update. Cần đồng bộ hóa hoặc chuyển sang cơ chế tăng nguyên tử phù hợp.

**Câu 6.** Trong ví dụ, tại sao sau **SetObjectField(label, nextLabel)** có thể gọi **DeleteLocalRef(nextLabel)**?

**Đáp án:** Setter đã lưu Java reference vào field. DeleteLocalRef chỉ xóa tham chiếu tạm JNI, không tự xóa đối tượng String mà Java field đang giữ.

**Câu 7.** GetFieldID tìm không thấy field thì có nên dùng ExceptionClear và tiếp tục GetIntField không?

**Đáp án:** Không. Lookup trả NULL và thường đang có pending NoSuchFieldError; phải xử lý lỗi hoặc trả về Java, không tiếp tục bằng ID vô hiệu. ExceptionClear chỉ có ý nghĩa khi thật sự có cơ chế recovery hợp lệ.

**Câu 8.** Có cần dùng method descriptor như **(I)V** để tìm field **int count** không?

**Đáp án:** Không. Field descriptor của int là **I**. Dấu ngoặc tròn nằm trong method descriptor, không dùng để tra field.

## Nguồn tham khảo

- [Oracle Java Native Interface Specification — JNI Functions: Accessing Fields of Objects / Accessing Static Fields](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html).
- [Oracle JNI Design Overview — Accessing Fields and Methods, Local/Global References, JNIEnv](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html).
- [Oracle JNI Types and Data Structures](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/types.html).
- [Oracle javac — tùy chọn -h sinh header JNI](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html).
- [Oracle JNI Invocation API — gắn native thread vào JVM](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/invocation.html).

**Điểm cốt lõi:** Trong JNI, việc đọc/ghi Java field đúng luôn bắt đầu bằng **đúng loại field (instance/static), đúng class và đúng descriptor**. Sau đó dùng **đúng Get/Set accessor theo kiểu** với đối số **jobject hoặc jclass** phù hợp; kiểm tra lỗi field ID, quản lý Java references và bảo đảm đồng bộ hóa/bất biến nghiệp vụ. Gọi sai họ hàm có thể gây hỏng dữ liệu hoặc lỗi JVM nghiêm trọng dù source C vẫn biên dịch được.
