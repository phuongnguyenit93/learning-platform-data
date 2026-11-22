# Nhúng JVM trong ứng dụng C và gọi một dịch vụ Java

**Chủ đề:** Java Advance – Native Interoperability  
**Nhóm bài:** Bài thực hành  
**Môi trường thực hành:** JDK 17+, trình biên dịch C11, Linux x86-64. Mã Java sử dụng cú pháp Java 17; những hệ điều hành khác cần điều chỉnh đường dẫn thư viện JVM và lệnh linker.

## 1. Kết quả cần đạt

Bạn có một chương trình C độc lập cần dùng nghiệp vụ đã được viết bằng Java. Thay vì chạy một chương trình Java bên ngoài rồi trao đổi qua stdin/HTTP, chương trình C có thể **nạp JVM vào chính tiến trình của nó** bằng **JNI Invocation API**, tìm lớp Java, tạo đối tượng service, gọi phương thức, nhận kết quả và chủ động kết thúc vòng đời JVM.

Sau bài này bạn sẽ:

1. Dùng **JNI_CreateJavaVM** để khởi tạo JVM từ ứng dụng C và thiết lập classpath.
2. Hiểu vai trò **JavaVM*** (đại diện JVM) và **JNIEnv*** (giao diện JNI gắn với *thread hiện tại*).
3. Tìm lớp Java, lấy constructor/method ID, tạo một service bằng **NewObject**, gọi phương thức instance bằng **CallObjectMethod**.
4. Truyền **String** và **int** từ C sang Java, nhận **String** trả về và giải phóng JNI reference/chuỗi được mượn.
5. Phát hiện và xử lý exception Java, gọi **close()** của service, rồi **DestroyJavaVM** an toàn.
6. Phân biệt ví dụ một thread với ứng dụng C nhiều thread, nắm quy tắc attach/detach và các giới hạn thực tế của JVM nhúng.

### Nhúng JVM hoạt động như thế nào?

~~~text
┌──────────────────────────── Tiến trình C ──────────────────────────────┐
│ main()                                                                │
│    │ JNI_CreateJavaVM, -Djava.class.path=classes                       │
│    ▼                                                                   │
│ JVM (libjvm.so) ── JNIEnv* của chính thread đang gọi                  │
│    │                                                                   │
│    ├── FindClass("demo/PriceService")                                │
│    ├── GetMethodID("<init>", "(J)V") + NewObject(...)                 │
│    ├── GetMethodID("quote", "(Ljava/lang/String;I)Ljava/lang/String;")│
│    ├── NewStringUTF("BOOK") → CallObjectMethod(...)                   │
│    ├── GetStringUTFChars(result) → in kết quả → Release...             │
│    ├── CallVoidMethod(service.close) + DeleteLocalRef                 │
│    └── DestroyJavaVM                                                   │
└────────────────────────────────────────────────────────────────────────┘
~~~

**Nhúng JVM (C → Java)** là chiều ngược với ví dụ JNI thường gặp **Java → hàm native C**. JNI Invocation API cấp JVM và thread context; bộ hàm JNI thông thường vẫn dùng để tạo/đọc object và gọi method. **Không cần Java có phương thức main()**: C là entry point của ứng dụng.

Cách này hợp lý khi ứng dụng chủ là C/C++, muốn tận dụng library Java đã có và chịu được chi phí JVM cùng nằm trong process. Nếu muốn cách ly lỗi native, deploy hoặc scale Java độc lập, IPC/HTTP/gRPC là hướng thiết kế khác; việc chọn kiến trúc dựa trên yêu cầu của hệ thống, không chỉ thời gian một lời gọi.

## 2. Thiết kế service Java và hợp đồng dữ liệu

Bài thực hành dùng **PriceService** để báo giá hai SKU, không cần framework hay máy chủ web:

- **BOOK**: 1.250 cent/sản phẩm.
- **PEN**: 175 cent/sản phẩm.
- Một lần gọi có **phí dịch vụ** (fee) 250 cent, cấu hình trong constructor.
- **quote(String sku, int quantity)** trả một chuỗi biên nhận: sản phẩm, số lượng, tổng tiền.
- **close()** đưa service sang trạng thái đã đóng. Gọi quote sau close sẽ ném **IllegalStateException**.

Tiền được biểu diễn bằng **số nguyên cent (long)** để ví dụ không phát sinh sai số biểu diễn tiền của double. Phép nhân/cộng sử dụng **Math.multiplyExact/Math.addExact**, báo lỗi khi tràn số. Service đồng bộ **quote()** và **close()** để một thao tác kiểm tra trạng thái rồi tính giá không đua với thao tác đóng. Đây là một mẫu service nghiệp vụ đơn giản; chưa có database, I/O hoặc pool.

| Ranh giới | Đầu vào Java | Kiểu JNI ở C | Ghi chú |
| --- | --- | --- | --- |
| Constructor PriceService(long) | long feeCents | **jlong** | Chữ ký **(J)V** |
| quote(String,int) | String sku, int quantity | **jstring**, **jint** | Chữ ký **(Ljava/lang/String;I)Ljava/lang/String;** |
| Giá trị từ quote | String | **jstring** | C phải lấy và release các ký tự được JNI cung cấp |
| close() | Không đối số, void | CallVoidMethod | Chữ ký **()V** |
| Java exception | Throwable | Trạng thái pending của JNIEnv | Phải kiểm tra sau thao tác JNI có thể ném lỗi |

**Ghi nhớ:** tên package Java dùng dấu chấm, ví dụ **demo.PriceService**; tên dùng với **FindClass** đổi thành **demo/PriceService**. Trong chữ ký JVM: **I=int**, **J=long**, **V=void**, **Lpackage/Class;=reference**, và dấu ngoặc tròn chứa các kiểu tham số. C gọi sai tên/chữ ký sẽ không tìm thấy phương thức, dù Java source rõ ràng có phương thức tên tương tự.

## 3. Cấu trúc tệp thực hành

Tạo dự án với đúng tên và vị trí:

~~~text
embed-jvm/
├── src/
│   └── demo/
│       └── PriceService.java
├── embed.c
└── classes/                     (javac tạo các file .class vào đây)
~~~

Đứng ở thư mục **embed-jvm/** khi biên dịch và chạy. Thư mục **classes/** là classpath runtime dùng trong đoạn C. Lệnh C có thể chạy từ đường dẫn khác, nhưng nếu working directory thay đổi, classpath tương đối **classes** cũng đổi theo; khi triển khai thật hãy truyền một **đường dẫn tuyệt đối đáng tin cậy** cho classpath.

### Tệp src/demo/PriceService.java

~~~java
package demo;

public final class PriceService implements AutoCloseable {
    private final long feeCents;
    private boolean closed;

    public PriceService(long feeCents) {
        if (feeCents < 0) {
            throw new IllegalArgumentException("feeCents must be nonnegative");
        }
        this.feeCents = feeCents;
    }

    public synchronized String quote(String sku, int quantity) {
        if (closed) {
            throw new IllegalStateException("service already closed");
        }
        if (sku == null || quantity <= 0) {
            throw new IllegalArgumentException("invalid sku or quantity");
        }
        long unitCents = switch (sku) {
            case "BOOK" -> 1250L;
            case "PEN" -> 175L;
            default -> throw new IllegalArgumentException("unknown sku: " + sku);
        };
        long total = Math.addExact(
                Math.multiplyExact(unitCents, quantity), feeCents);
        return sku + " x" + quantity + " => " + total + " cents";
    }

    @Override
    public synchronized void close() {
        closed = true;
    }
}
~~~

**Đọc mã:** Constructor nhận phí cố định cho mỗi yêu cầu báo giá. Mỗi cuộc gọi quote tra đơn giá, kiểm tra quantity, tính giá và tạo chuỗi; với **BOOK x3**, tổng là **1.250 × 3 + 250 = 4.000 cent**. Vì service do C tạo và giữ, C phải quyết định lúc nào gọi close. Trong ví dụ này close chỉ đánh dấu trạng thái; trong service thực, close còn có thể đóng kết nối, giải phóng các tài nguyên do service sở hữu.

Service Java không có main(), vì main() là ở C. Nó không sử dụng Spring; trong hệ thống dùng Spring, chương trình C cần gọi một facade Java chịu trách nhiệm khởi động và đóng **ApplicationContext** trước/sau các nghiệp vụ.

## 4. Chương trình C đầy đủ dùng JNI Invocation API

Đoạn C dưới đây dùng JNI theo đúng cú pháp C (gọi qua bảng con trỏ hàm **(*env)->...** và **(*jvm)->...**). C++ có cú pháp gọi tương ứng khác (**env->...**, **jvm->...**), nên không thay file .c thành .cpp mà vẫn giữ nguyên giả định API kiểu C.

### Tệp embed.c

~~~c
#include <jni.h>
#include <stdio.h>
#include <stdlib.h>

static int report_java_error(JNIEnv *env, const char *operation) {
    if (!(*env)->ExceptionCheck(env)) {
        return 0;
    }
    fprintf(stderr, "Java exception at %s:\n", operation);
    (*env)->ExceptionDescribe(env);
    (*env)->ExceptionClear(env);
    return 1;
}

static int print_quote(JNIEnv *env, jobject service,
                       jmethodID quote, const char *sku, jint quantity) {
    jstring javaSku = NULL;
    jstring result = NULL;
    const char *utf8 = NULL;
    int success = 0;

    javaSku = (*env)->NewStringUTF(env, sku);
    if (report_java_error(env, "NewStringUTF") || javaSku == NULL) {
        goto cleanup;
    }

    result = (jstring)(*env)->CallObjectMethod(
            env, service, quote, javaSku, quantity);
    if (report_java_error(env, "PriceService.quote") || result == NULL) {
        goto cleanup;
    }

    utf8 = (*env)->GetStringUTFChars(env, result, NULL);
    if (report_java_error(env, "GetStringUTFChars") || utf8 == NULL) {
        goto cleanup;
    }
    puts(utf8);
    success = 1;

cleanup:
    if (utf8 != NULL) {
        (*env)->ReleaseStringUTFChars(env, result, utf8);
    }
    if (result != NULL) {
        (*env)->DeleteLocalRef(env, result);
    }
    if (javaSku != NULL) {
        (*env)->DeleteLocalRef(env, javaSku);
    }
    return success ? 0 : 1;
}

int main(void) {
    JavaVM *jvm = NULL;
    JNIEnv *env = NULL;
    char classpath[] = "-Djava.class.path=classes";
    JavaVMOption options[] = {{classpath, NULL}};
    JavaVMInitArgs args = {0};
    args.version = JNI_VERSION_1_8;
    args.nOptions = 1;
    args.options = options;
    args.ignoreUnrecognized = JNI_FALSE;

    jint rc = JNI_CreateJavaVM(&jvm, (void **)&env, &args);
    if (rc != JNI_OK || jvm == NULL || env == NULL) {
        fprintf(stderr, "Cannot start JVM: code %d\n", (int)rc);
        return EXIT_FAILURE;
    }

    int status = EXIT_FAILURE;
    jclass serviceClass = NULL;
    jobject service = NULL;
    jmethodID closeMethod = NULL;

    serviceClass = (*env)->FindClass(env, "demo/PriceService");
    if (report_java_error(env, "FindClass") || serviceClass == NULL) {
        goto cleanup;
    }

    jmethodID constructor = (*env)->GetMethodID(
            env, serviceClass, "<init>", "(J)V");
    if (report_java_error(env, "GetMethodID(<init>)") || constructor == NULL) {
        goto cleanup;
    }

    jmethodID quoteMethod = (*env)->GetMethodID(
            env, serviceClass, "quote",
            "(Ljava/lang/String;I)Ljava/lang/String;");
    if (report_java_error(env, "GetMethodID(quote)") || quoteMethod == NULL) {
        goto cleanup;
    }

    closeMethod = (*env)->GetMethodID(env, serviceClass, "close", "()V");
    if (report_java_error(env, "GetMethodID(close)") || closeMethod == NULL) {
        goto cleanup;
    }

    service = (*env)->NewObject(env, serviceClass, constructor, (jlong)250);
    if (report_java_error(env, "NewObject") || service == NULL) {
        goto cleanup;
    }

    if (print_quote(env, service, quoteMethod, "BOOK", 3) != 0 ||
        print_quote(env, service, quoteMethod, "PEN", 2) != 0) {
        goto cleanup;
    }
    status = EXIT_SUCCESS;

cleanup:
    if (service != NULL && closeMethod != NULL) {
        (*env)->CallVoidMethod(env, service, closeMethod);
        if (report_java_error(env, "PriceService.close")) {
            status = EXIT_FAILURE;
        }
    }
    if (service != NULL) {
        (*env)->DeleteLocalRef(env, service);
    }
    if (serviceClass != NULL) {
        (*env)->DeleteLocalRef(env, serviceClass);
    }
    if ((*jvm)->DestroyJavaVM(jvm) != JNI_OK) {
        fprintf(stderr, "JVM shutdown failed\n");
        status = EXIT_FAILURE;
    }
    if (status == EXIT_SUCCESS) {
        puts("JVM stopped");
    }
    return status;
}
~~~

### Vì sao C được chia thành hai hàm phụ?

**report_java_error** là nơi duy nhất ghi nhận exception Java sau các thao tác JNI có thể thất bại. **ExceptionCheck** cho biết có exception đang pending; **ExceptionDescribe** in stack trace ra kênh lỗi, còn **ExceptionClear** đảm bảo đường cleanup tiếp tục trong trạng thái không có exception. ExceptionDescribe vốn cũng có tác dụng làm sạch exception pending theo đặc tả, nên ExceptionClear sau đó là bước phòng vệ dễ đọc. Trong production, nên trả exception/error code theo contract của ứng dụng; in stack trace trực tiếp là công cụ học/debug.

**print_quote** giữ các JNI local references **javaSku** và **result**, cũng như con trỏ ký tự **utf8** chỉ sống cho đến khi **ReleaseStringUTFChars**. Mọi lối thoát đều đi qua nhánh **cleanup**, nên một lỗi giữa chừng không bỏ quên resource. Hai lần gọi C sử dụng **chính đối tượng service** đã tạo, minh họa reuse object/method ID.

**main** là owner của JVM. Sau khi JNI_CreateJavaVM trả **JNI_OK**, main dùng **JNIEnv*** thuộc thread vừa tạo JVM, tìm service, dựng đối tượng và gọi quote. Trước khi DestroyJavaVM, main gọi Java close, xóa local refs rồi kiểm tra mã trả của DestroyJavaVM. **Không gọi bất kỳ hàm JNI nào qua env sau khi DestroyJavaVM đã thành công**.

Không giữ local reference qua một session dài hoặc chuyển local reference sang thread khác. Đặc biệt, **JNIEnv*** không phải pointer có thể dùng từ mọi thread: nó là giao diện gắn với **thread hiện tại**.

## 5. Biên dịch và chạy

### Yêu cầu

- Linux x86-64 có **JDK 17 hoặc mới hơn** và compiler C hỗ trợ C11 (ví dụ GCC).
- **JAVA_HOME** trỏ tới thư mục gốc JDK, bên trong có **include/jni.h**, **include/linux/jni_md.h**, **lib/server/libjvm.so**.
- Terminal đang ở thư mục **embed-jvm/**. Mã C dùng classpath **classes**, có nghĩa **./classes** từ working directory của tiến trình C.
- Không cần Gradle, Maven, web server, JAR hay process Java riêng để chạy ví dụ.

### Các lệnh

~~~bash
# Đứng trong thư mục embed-jvm/ và bảo đảm JAVA_HOME đã đặt.
mkdir -p classes
javac -d classes src/demo/PriceService.java

gcc -std=c11 -Wall -Wextra -Werror -O2 \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  embed.c -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embed

./embed
~~~

**stdout mong đợi khi chạy thành công:**

~~~text
BOOK x3 => 4000 cents
PEN x2 => 600 cents
JVM stopped
~~~

Giải thích phép tính: BOOK = 1.250 × 3 + 250 = 4.000; PEN = 175 × 2 + 250 = 600 cent. Ba dòng trên có thứ tự xác định vì hai lời gọi Java chạy tuần tự từ một native thread. Trường hợp gặp lỗi sẽ in stderr và trả exit code khác 0; trace cụ thể phụ thuộc lỗi.

Lệnh **javac** tạo **classes/demo/PriceService.class**. **gcc** dùng **jni.h** và header ABI của Linux để biên dịch, liên kết **libjvm.so** thông qua **-L... -ljvm**. Tùy chọn **-Wl,-rpath,...** nhúng đường dẫn tìm libjvm khi loader chạy executable, giúp tránh lỗi thiếu libjvm.so trên máy thí nghiệm. Với bản phát hành thực tế, lựa chọn rpath, đường dẫn runtime và cách đóng gói JVM phải tuân theo chính sách deploy; không hardcode đường dẫn JDK của một máy phát triển.

Lệnh **java** thông thường không xuất hiện ở bước chạy vì chính **./embed** nạp JVM và kích hoạt lớp Java qua JNI. Bạn vẫn dùng **java -version** và **javac -version** để xác định công cụ JDK; **JNI_CreateJavaVM** thay vai trò khởi động JVM của Java launcher trong ví dụ này.

**Kiểm chứng thực tế:** Mã trên tương thích cú pháp Java 17 và C11. Có thể biên dịch Java bằng **javac --release 17** nếu máy dùng JDK mới và muốn kiểm tra API/language level của JDK 17. Java bytecode vẫn cần JVM hỗ trợ phiên bản class tương ứng.

### Khác biệt theo hệ điều hành

| Hệ điều hành | Header phụ thuộc OS | Thư viện JVM và lưu ý |
| --- | --- | --- |
| Linux | **$JAVA_HOME/include/linux** | **libjvm.so**, đường dẫn loader qua rpath hoặc cấu hình môi trường. |
| macOS | **$JAVA_HOME/include/darwin** | **libjvm.dylib**, linker/loader path theo cách đóng gói JDK trên macOS. |
| Windows | **%JAVA_HOME%\\include\\win32** | **jvm.dll**, linker thường cần import library tương ứng (ví dụ jvm.lib) và đường dẫn DLL phù hợp. |

Không dùng nguyên lệnh gcc/Linux trên Windows mà mong nó tìm đúng jvm.dll. Ngoài ra, executable native và JVM phải tương thích **kiến trúc/ABI (ví dụ cùng x86-64 hoặc cùng ARM64)**.

## 6. Đọc sâu từng bước của lời gọi JNI

### 6.1. Tạo JVM và cấu hình

~~~c
JavaVM *jvm = NULL;
JNIEnv *env = NULL;
char classpath[] = "-Djava.class.path=classes";
JavaVMOption options[] = {{classpath, NULL}};
JavaVMInitArgs args = {0};

args.version = JNI_VERSION_1_8;
args.nOptions = 1;
args.options = options;
args.ignoreUnrecognized = JNI_FALSE;

jint rc = JNI_CreateJavaVM(&jvm, (void **)&env, &args);
~~~

Đây là **đoạn rút ra từ embed.c**, không phải chương trình C độc lập. **JNI_VERSION_1_8** yêu cầu một phiên bản JNI tương thích, không ép JVM runtime xuống Java 8. Vì service dùng cú pháp Java 17 nên runtime thực tế vẫn phải là JDK 17+. Có thể thêm các startup options như **-Xmx512m**, **-Dapp.env=test**, **-XX:NativeMemoryTracking=summary** bằng những phần tử bổ sung của mảng JavaVMOption và sửa nOptions cho khớp. Các option cần thiết phải được cung cấp lúc tạo JVM; không giả định có thể chỉnh mọi startup flag sau khi VM đã chạy.

**JVM nằm trong cùng process**: Java heap, GC, runtime threads và native memory của JVM cùng tiêu thụ CPU/RAM/địa chỉ trong process C. Một native crash hoặc memory corruption nguy hiểm có thể khiến cả process lỗi. **Đừng tạo/destroy một JVM cho mỗi request**; nên có một JVM được quản lý trong vòng đời host.

### 6.2. Tìm class, constructor và method

Các lời gọi từ ví dụ:

| Câu lệnh JNI | Tìm gì? |
| --- | --- |
| **FindClass("demo/PriceService")** | Lớp phải nhìn thấy từ class loader phù hợp. |
| **GetMethodID("<init>", "(J)V")** | Constructor instance nhận long. |
| **NewObject(..., (jlong)250)** | Tạo PriceService với feeCents = 250. |
| **GetMethodID("quote", "(Ljava/lang/String;I)Ljava/lang/String;")** | Phương thức instance trả String từ String và int. |
| **GetMethodID("close", "()V")** | close() trả void. |
| **CallObjectMethod** | Gọi phương thức instance trả reference. |
| **CallVoidMethod** | Gọi close() và không có giá trị trả về. |

**GetMethodID** dùng cho instance method; với **static method**, dùng **GetStaticMethodID/CallStatic...Method** trên class. Chữ ký overload phải chính xác: gọi phương thức có cùng tên nhưng khác kiểu sẽ thất bại nếu nhầm descriptor. Nếu đổi package, method, constructor hoặc return type ở Java, phải cập nhật descriptor ở C.

Trong một ứng dụng có custom class loader (plugin loader, container hoặc framework), **FindClass** từ native thread mới attach có thể không tìm được class nằm ngoài system/application classpath. Khi đó Java facade hoặc ClassLoader.loadClass của một loader được quản lý mới là ranh giới rõ ràng, thay vì dò lại tên class ngẫu nhiên.

### 6.3. Chuỗi và local references

**NewStringUTF** tạo Java String từ **Modified UTF-8**, không phải một hàm tổng quát cho mọi chuỗi UTF-8 tùy ý. Ví dụ dùng các SKU ASCII **BOOK/PEN**, nên byte đầu vào hợp lệ. Với dữ liệu Unicode từ C (đặc biệt NUL và supplementary code points), cần chuyển đổi đúng sang **jchar/UTF-16** rồi dùng **NewString**, hoặc một hợp đồng encoding được kiểm thử chặt; không mặc định byte UTF-8 thường luôn hợp lệ với NewStringUTF.

**GetStringUTFChars** trả con trỏ ký tự theo Modified UTF-8, có thể là copy và có thể thất bại vì thiếu bộ nhớ. **ReleaseStringUTFChars** là bắt buộc để trả tài nguyên JNI trước khi xóa local reference/result hoặc kết thúc. Không gọi free() trên pointer này. **DeleteLocalRef** xóa reference JNI (cho phép GC quản lý object Java khi không còn reference khác); nó không trực tiếp giải phóng object bằng free().

Trong vòng lặp gọi hàng chục nghìn request, luôn xóa local refs sau mỗi lượt hoặc dùng PushLocalFrame/PopLocalFrame; chỉ vì đang ở C không có nghĩa local refs tự biến mất sau mỗi lần gọi JNI từ host. Một thread được attach và hoạt động lâu có thể giữ nhiều local refs nếu không release.

### 6.4. Java exception và kết quả lỗi

Java exception được giữ dưới dạng **pending exception trên JNIEnv hiện tại**; việc hàm JNI trả NULL sau một thao tác thất bại không phải mô hình exception của C. Quy trình phải:

1. Kiểm tra **ExceptionCheck** sau những lệnh như FindClass, GetMethodID, NewObject và CallObjectMethod.
2. Ghi thông tin/đổi thành error code theo contract. Bài học dùng **ExceptionDescribe** để hiện stack trace khi debug.
3. Làm sạch pending exception nếu bên C sẽ tiếp tục thực hiện lời gọi JNI/cleanup thông thường, hoặc có chủ đích truyền ngược exception khi là native method được Java gọi.
4. Không xử lý giá trị trả từ một lời gọi đã thất bại như object hợp lệ.

Hãy thử thay một SKU trong **embed.c** từ **"BOOK"** thành **"UNKNOWN"**, biên dịch lại C và chạy. Phương thức Java sẽ ném **IllegalArgumentException: unknown sku: UNKNOWN**, phía C mô tả exception, bỏ nhánh thành công, dọn local refs, đóng service và destroy JVM trước khi trả exit code lỗi. Nội dung stack trace có thể thay đổi theo runtime, nên không đặt stdout cố định cho ca lỗi.

## 7. Vòng đời JVM khi nhúng vào tiến trình C

Bài thực hành tạo JVM một lần, gọi service rồi destroy. Ứng dụng thực tế nên có vòng đời:

1. **Process initialization:** xác định phiên bản JVM, classpath, JVM options, tài nguyên cấp phát và logging. Nếu host C có nhiều thread, xác định thread chuyên khởi tạo JVM và chịu trách nhiệm API lifecycle.
2. **JVM startup:** gọi JNI_CreateJavaVM **một lần**; kiểm tra **JNI_OK**, đưa dịch vụ Java vào trạng thái sẵn sàng, cache class/method handles hợp lệ.
3. **Serving:** các native threads cần tương tác với Java phải attach; gọi service đã đồng bộ; báo lỗi và metrics rõ ràng.
4. **Quiesce:** ngừng tiếp nhận request mới, đợi công việc đang chạy/Java callback hoàn tất, ngừng các resource worker.
5. **Service shutdown:** gọi close()/stop() của service; xóa global refs trong lúc JNIEnv còn hợp lệ.
6. **JVM shutdown:** gọi DestroyJavaVM và kiểm tra kết quả; chấm dứt process hoặc tiếp tục công việc C không dùng JNI.

**DestroyJavaVM** có thể phải đợi các Java thread/native attached thread không phải daemon kết thúc; nếu một worker chưa detach hoặc vẫn làm việc, thao tác destroy có thể chờ rất lâu. Không dùng kill/force-free để “sửa” lịch shutdown; trước hết phải lập thứ tự dừng chính xác và có timeout/giám sát ở tầng ứng dụng.

**Giới hạn lớn:** JNI Invocation API không hỗ trợ tạo nhiều JVM độc lập trong cùng process. Cũng không nên thiết kế việc destroy rồi tạo lại JVM trong cùng process như một “restart service” thông thường; khả năng khởi động lại sau destroy không phải lifecycle có thể dựa vào. Nếu cần restart độc lập, tách process. Cần lập kế hoạch cho chi phí khởi động JVM, tải class, JIT warm-up và thread/heap footprint.

Tài liệu Invocation API còn khuyến nghị **tránh khởi tạo JVM trên primordial thread** ở một số hệ điều hành vì hạn chế về stack/signal. Ví dụ ngắn dùng main() để dễ học, còn host C chạy thật nên kiểm soát thread tạo JVM và stack size, đồng thời đánh giá signal handling trên nền tảng triển khai.

## 8. Khi C có nhiều native threads

**JavaVM*** là handle JVM có thể dùng để **attach các thread phù hợp**. **JNIEnv*** chỉ hợp lệ cho *thread sở hữu nó*, không được cache một JNIEnv* chung rồi chia cho pthread. Một native worker chưa attach có thể làm như sau:

~~~c
/* Minh họa trong một hàm native worker, không phải chương trình độc lập. */
JNIEnv *workerEnv = NULL;
if ((*jvm)->AttachCurrentThread(jvm, (void **)&workerEnv, NULL)
        != JNI_OK) {
    /* Báo lỗi attach cho hệ thống C. */
    return;
}

/* Gọi Java qua workerEnv; kiểm tra exception và dọn local refs.
   Không sử dụng env của thread khởi tạo JVM. */

jint detachResult = (*jvm)->DetachCurrentThread(jvm);
/* Ghi nhận lỗi nếu detachResult != JNI_OK. */
~~~

**AttachCurrentThread** không tự tạo một JVM mới; nó gắn thread hiện tại vào JVM đã tồn tại. Một thread đã attach mà attach lần nữa sẽ nhận context thread đã có. Phải detach **trước khi native thread kết thúc** và không detach khi vẫn có Java frame đang chạy trên stack. Nếu thread gọi Java callback hoặc giữ monitor, phải hoàn tất công việc và release resource trước khi detach.

Nếu object **service** được dùng sau khi local JNI frame ban đầu kết thúc, hoặc chuyển sang worker thread khác, chủ sở hữu cần **NewGlobalRef** (và cuối cùng **DeleteGlobalRef**) thay vì chuyển thẳng một local jobject. Global reference chỉ duy trì khả năng tham chiếu object; **không** giúp service tự trở thành thread-safe. Worker phải dùng cơ chế đồng bộ đúng của Java service, giới hạn mức concurrency, và ngừng xếp việc mới trước khi xóa global ref hoặc DestroyJavaVM.

**Khác biệt daemon:** AttachCurrentThreadAsDaemon đánh dấu native thread mới attach là daemon Java thread; sự khác biệt ảnh hưởng shutdown. Không chọn daemon chỉ để DestroyJavaVM khỏi chờ nếu worker có thể còn dùng Java state/native memory sau shutdown.

## 9. Gọi dịch vụ thuộc framework (ví dụ Spring) qua một facade

PriceService trong bài là lớp Java thuần, nên chỉ cần constructor. Nếu nghiệp vụ là một Spring bean với dependency injection, transaction, datasource và cấu hình, việc gọi **NewObject** trên bean class sẽ bỏ qua Spring container; nhiều annotation như **@Transactional**, injection và proxy có thể không hoạt động như thiết kế.

Hãy đưa việc boot/stop framework vào một **Java facade** với API ổn định, rồi để C gọi các phương thức facade qua JNI. Một hướng thiết kế (đây chỉ là phác thảo Java, **không phải một tệp runnable độc lập**):

~~~java
// Java facade minh họa; cần dependency và cấu hình Spring phù hợp.
// public static synchronized void start(String[] args) {
//     context = SpringApplication.run(MyApplication.class, args);
// }
// public static String quote(String sku, int count) {
//     return context.getBean(PriceService.class).quote(sku, count);
// }
// public static synchronized void stop() {
//     if (context != null) context.close();
// }
~~~

Tầng facade chuyển kiểu dữ liệu, chuẩn hóa exception, lấy bean và quản lý container. C chỉ biết tên/chữ ký facade mà không phải tìm hiểu đường wiring nội bộ của Spring. Khởi động Spring context có chi phí và thường sinh background threads, nên stop() + đóng tài nguyên phải hoàn tất trước DestroyJavaVM. Không đặt nhiều context không kiểm soát vào từng request.

Trong môi trường module/automatic modularity, **-Djava.class.path** chỉ phục vụ classpath truyền thống. Nếu ứng dụng Java yêu cầu module path/--module-path, native image hay class loader đặc thù, cần cấu hình tương ứng và kiểm chứng quyền truy cập package/reflective access; không mặc định chuyển một fat JAR hoặc module production sang JNI embed mà không xử lý runtime dependencies.

## 10. Lỗi phổ biến và chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| **Cannot start JVM: code ...** | Sai libjvm, JVM option, kiến trúc hoặc runtime không tương thích | Đối chiếu JAVA_HOME, bitness, linker/loader, startup options và exit code. |
| **libjvm.so: cannot open shared object file** | Loader không tìm được shared library trước cả JNI_CreateJavaVM | Kiểm tra rpath, đường dẫn JDK runtime, chính sách phân phối thư viện. |
| **NoClassDefFoundError: demo/PriceService** | Classpath không trỏ đến classes hoặc Java class/module dependencies thiếu | Đứng đúng working directory; kiểm tra classes/demo/PriceService.class và -Djava.class.path. |
| **NoSuchMethodError** | Sai tên, chữ ký, static/instance, overload hay phiên bản Java class | Đối chiếu descriptor với bytecode qua javap -s. |
| **JVM crash sau khi giải phóng string** | Dùng con trỏ trả từ GetStringUTFChars sau Release hoặc giải phóng sai hàm | Chỉ dùng trong khoảng được mượn, ReleaseStringUTFChars đúng một lần. |
| **JNI calls thất bại không rõ nguyên nhân** | Còn pending exception hoặc dùng jobject/JNIEnv không hợp lệ | ExceptionCheck/Describe/Clear, kiểm tra phạm vi local/global reference và thread. |
| **Gọi Java từ pthread bị lỗi/crash** | Native thread chưa AttachCurrentThread hoặc dùng JNIEnv của thread khác | Attach từng native worker, dùng JNIEnv riêng, detach trước khi thread kết thúc. |
| **DestroyJavaVM chờ lâu** | Non-daemon thread hoặc callback/worker còn sống | Quiesce request, close service/context, join/detach thread rồi destroy. |
| **Dịch vụ chạy nhưng hành vi Spring sai** | NewObject bypass dependency injection/proxy | Gọi qua Java facade khởi động container và lấy bean đúng cách. |
| **Đầu ra Unicode hỏng** | Dùng UTF-8 thường như Modified UTF-8, sai converter | Thiết kế encoding cụ thể; dùng NewString/UTF-16 cho chuỗi Unicode bất kỳ. |

**Mẹo kiểm tra:**

- **javap -classpath classes -s demo.PriceService** cho biết JVM descriptor của constructor và method; luôn tin descriptor từ bytecode hơn việc đoán.
- **java -version**, **javac -version** xác minh phiên bản JDK; **ldd ./embed** (Linux) giúp xem dependency libjvm; **file ./embed** có thể xác nhận kiến trúc executable.
- Thử **-Xcheck:jni** trong mảng JVM options để phát hiện nhiều trường hợp dùng JNI không hợp lệ, nhưng không coi kết quả sạch là chứng minh hết memory race/lifetime bug.
- Khi debug lỗi JVM startup, ghi rõ **exit code**, stdout/stderr và lựa chọn JVM options, thay vì chỉ in “service failed”.
- Nếu host C chạy lâu, thêm số lượng native threads đã attach, global reference ownership, JVM/heap/direct/native memory, độ trễ JNI call và tỷ lệ lỗi Java→C translation. Quan sát cả GC và thời gian chờ synchronized lock.

## 11. Bài tập mở rộng và tiêu chí đạt

1. **Đường thành công:** biên dịch hai tệp, xác nhận đúng ba dòng stdout; thử thay phí constructor thành 0 và tự tính kết quả mới.
2. **Đường exception:** đổi **"BOOK" → "UNKNOWN"** trong C, rebuild, xác nhận Java exception được báo và ứng dụng vẫn đi qua cleanup/DestroyJavaVM; không lấy kết quả lỗi làm String hợp lệ.
3. **Phần chữ ký:** chạy **javap -s**, đối chiếu **(J)V**, **(Ljava/lang/String;I)Ljava/lang/String;**, **()V** với C; thử thay kiểu tham số ở Java để thấy cần cập nhật JNI.
4. **Vòng đời:** sau **close()**, thử gọi lại **quote()** để xác nhận IllegalStateException; sau khi **DestroyJavaVM** không dùng lại JNIEnv* cũ.
5. **Classpath:** chạy chương trình từ working directory khác để tái hiện lỗi, rồi sửa classpath thành đường dẫn tuyệt đối do host cấu hình.
6. **Nhiều luồng (phần nâng cao):** cho một native worker thread attach, gọi Java service bằng reference có ownership đúng, dọn local refs, detach, join; chỉ destroy sau khi worker hoàn tất. Bổ sung test race giữa quote và close theo contract.
7. **Đo hiệu năng:** đo cold startup JVM riêng với thời gian quote sau warm-up; so JNI call end-to-end với thời gian nghiệp vụ, thống kê p95/p99 khi lặp. Không đánh đồng latency khởi tạo JVM với latency mỗi lời gọi.
8. **Tích hợp thực tế:** nếu thay PriceService bằng bean Spring, bổ sung facade Java để boot ApplicationContext một lần, gọi bean, và stop() trước khi destroy VM.

**Hoàn thành bài khi:** một executable **C** tự tạo JVM, tìm đúng **demo.PriceService**, gọi ít nhất hai thao tác Java có kết quả, xử lý exception theo contract, trả mọi tài nguyên JNI được mượn, đóng service, kiểm tra DestroyJavaVM và giải thích được vì sao JNIEnv* là riêng cho từng thread.

## Tài liệu chuẩn

- [JNI Specification, Chapter 5 – Invocation API (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): JNI_CreateJavaVM, JavaVMInitArgs, AttachCurrentThread, DetachCurrentThread, DestroyJavaVM và giới hạn vòng đời.
- [JNI Functions (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): FindClass, GetMethodID, NewObject, CallObjectMethod, exception, string và local/global references.
- [Java Virtual Machine Specification §4.3 – Descriptors (Java 17)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3): quy tắc mô tả type/method signature của JVM.
- [javap command (JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): in chữ ký method từ class đã biên dịch.
