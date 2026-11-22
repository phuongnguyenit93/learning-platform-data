# Tạo chuỗi, đọc độ dài theo đơn vị ký tự hoặc byte và xử lý dữ liệu lớn trong JNI

## Mục tiêu bài học

Java Native Interface (JNI) cho phép C/C++ tạo đối tượng **java.lang.String**, đọc nội dung của chuỗi Java và chuyển dữ liệu qua ranh giới JVM–native. Tuy nhiên, thao tác với chuỗi chỉ an toàn khi phân biệt rõ **đơn vị UTF-16**, **Unicode code point**, **số byte theo từng encoding**, **vòng đời vùng nhớ** và **kích thước dữ liệu**.

Sau bài này, bạn có thể:

1. Sử dụng **NewString** với dữ liệu UTF-16 và **NewStringUTF** với dữ liệu **modified UTF-8** hợp lệ.
2. Hiểu chính xác **GetStringLength** đếm đơn vị mã UTF-16, còn **GetStringUTFLength** và **GetStringUTFLengthAsLong** đếm byte của modified UTF-8.
3. Phân biệt độ dài Java String, số Unicode code point, UTF-8 chuẩn và modified UTF-8 của JNI, kể cả ký tự U+0000 và ký tự ngoài BMP.
4. Đọc chuỗi bằng **GetStringChars**, **GetStringUTFChars** hoặc các hàm **GetStringRegion / GetStringUTFRegion**; giải phóng tài nguyên đúng cặp API.
5. Xử lý chuỗi lớn theo từng đoạn, giới hạn cấp phát, tránh phép nhân kích thước bị tràn và không giữ critical region quá lâu.
6. Xây dựng, chạy và kiểm tra ví dụ Java 17+ kết hợp C/JNI, với stdout xác định và kết quả giải thích được.

## 1. Ba khái niệm độ dài không được đánh đồng

Một Java String biểu diễn một dãy **UTF-16 code units** (đơn vị 16 bit). Java **String.length()** và JNI **GetStringLength** trả về số đơn vị UTF-16 đó. Một Unicode code point nằm ngoài Basic Multilingual Plane (BMP) cần **hai code units** (surrogate pair); vì vậy số code point có thể khác chiều dài String.

Độ dài tính bằng **byte** chỉ có nghĩa sau khi chọn encoding. Trong thực tế có ít nhất hai loại cần phân biệt khi làm JNI:

- **UTF-8 chuẩn** dùng trong file, HTTP, JSON, nhiều giao thức mạng và **String.getBytes(StandardCharsets.UTF_8)** của Java.
- **Modified UTF-8 (MUTF-8)** dùng bởi một số API JNI như **NewStringUTF**, **GetStringUTFChars**, **GetStringUTFLength** và **GetStringUTFRegion**. MUTF-8 xử lý ký tự U+0000 và ký tự bổ sung khác UTF-8 chuẩn.

Ví dụ cùng một chuỗi gồm **A**, ký tự null Unicode **U+0000**, **é** và emoji **🙂** (U+1F642):

| Thành phần | UTF-16 code units | Byte UTF-8 chuẩn | Byte JNI modified UTF-8 |
| --- | ---: | ---: | ---: |
| A (U+0041) | 1 | 1 | 1 |
| U+0000 | 1 | 1 | 2 |
| é (U+00E9) | 1 | 2 | 2 |
| 🙂 (U+1F642) | 2 | 4 | 6 |
| **Tổng** | **5** | **8** | **11** |

Chuỗi có **4 Unicode code points**, nhưng **5 UTF-16 code units**. UTF-8 chuẩn chiếm **8 byte**, còn modified UTF-8 chiếm **11 byte**. Không có một giá trị “số ký tự” duy nhất đúng cho mọi nhu cầu; phải phát biểu rõ đơn vị đo.

### Vì sao modified UTF-8 khác UTF-8 chuẩn?

Trong MUTF-8 của JNI:

- **U+0000** được mã hóa bằng hai byte **C0 80** thay vì byte **00**, nên dữ liệu MUTF-8 hợp lệ không chứa byte null ở giữa chuỗi. Điều này phù hợp với một số API C coi **00** là dấu kết thúc chuỗi.
- Các code point ngoài BMP được biểu diễn thành **cặp UTF-16 surrogate**; mỗi code unit surrogate được mã hóa thành **3 byte**, tổng cộng **6 byte** cho một code point như 🙂. UTF-8 chuẩn mã hóa nó bằng **4 byte**.
- Các ký tự ASCII khác U+0000 vẫn dùng một byte, nên chuỗi chỉ có ASCII thường làm chúng ta tưởng UTF-8 chuẩn và MUTF-8 hoàn toàn giống nhau.

**Không chuyển trực tiếp byte UTF-8 chuẩn tùy ý vào NewStringUTF.** Byte UTF-8 chứa ký tự 4 byte hoặc byte null ở giữa không thỏa hợp đồng MUTF-8 của hàm này. Nếu dữ liệu đến từ file/network, hãy decode bằng charset chuẩn có kiểm soát, hoặc chuyển đổi encoding trước khi gọi API JNI tương ứng.

## 2. Những API JNI cần biết

| API | Mục đích | Đơn vị/dữ liệu | Yêu cầu quan trọng |
| --- | --- | --- | --- |
| **NewString(env, jchar*, len)** | Tạo Java String | **len** UTF-16 code units | Có thể chứa U+0000; pointer còn hiệu lực trong thời gian gọi |
| **NewStringUTF(env, char*)** | Tạo Java String từ chuỗi C | Dãy byte **MUTF-8** kết thúc bằng null C | Input phải đúng MUTF-8, không phải UTF-8 chuẩn tùy ý |
| **GetStringLength(env, jstring)** | Độ dài String | **jsize** đếm UTF-16 code units | Không phải code points hoặc byte |
| **GetStringUTFLength(env, jstring)** | Độ dài biểu diễn MUTF-8 | **jsize** byte MUTF-8 | API đã deprecated trong JDK 24+; có giới hạn kích thước |
| **GetStringUTFLengthAsLong(env, jstring)** | Độ dài MUTF-8 cho chuỗi lớn | **jlong** byte MUTF-8 | **Có từ JDK 24**; không có trong JNI header của JDK 17 |
| **GetStringChars / ReleaseStringChars** | Mượn/có bản sao dữ liệu UTF-16 | **const jchar*** | Luôn release sau khi thành công |
| **GetStringUTFChars / ReleaseStringUTFChars** | Mượn/có bản sao dữ liệu MUTF-8 | **const char*** | Luôn release sau khi thành công |
| **GetStringRegion** | Sao chép một đoạn sang buffer do C cung cấp | offset/len theo UTF-16 code units | Kiểm soát vùng nhớ và ranh giới |
| **GetStringUTFRegion** | Chuyển một đoạn UTF-16 sang MUTF-8 trong buffer | offset/len là code units; output là **byte** | Buffer cần lớn hơn số code units và không bảo đảm NUL terminator |
| **GetStringCritical / ReleaseStringCritical** | Truy cập UTF-16 trong critical region | **const jchar*** | Không block hay gọi tùy tiện JNI API bên trong vùng critical |

Các API trên là **hàm của JNIEnv** trong C. Trong C++, JNI cung cấp cú pháp gọi khác nhưng ý nghĩa và các ràng buộc tương đương.

**jsize** là số nguyên có dấu 32 bit của JNI. Nó phù hợp với chỉ số và độ dài String/array Java, nhưng **không đủ** biểu diễn mọi độ dài byte MUTF-8 có thể có: mỗi UTF-16 code unit có thể cần tới 3 byte.

## 3. Tạo Java String từ native code

### 3.1. NewString: đầu vào UTF-16 với độ dài tường minh

Chữ ký:

~~~c
jstring NewString(JNIEnv *env, const jchar *unicodeChars, jsize len);
~~~

**jchar** là đơn vị 16 bit không dấu tương ứng với Java char. **len** là số phần tử jchar, **không phải byte count** và **không phải số Unicode code points**.

Ví dụ:

~~~c
const jchar units[] = {
    0x0041,  // A
    0x0000,  // U+0000 thật, không kết thúc mảng
    0x00E9,  // é
    0xD83D,  // high surrogate của U+1F642
    0xDE42   // low surrogate của U+1F642
};

jstring value = (*env)->NewString(env, units, 5);
if (value == NULL) {
    return; // JVM có thể đã ném OutOfMemoryError.
}
~~~

Đây là **snippet C trong native method**, giả sử có sẵn JNIEnv và kiểu trả về phù hợp; chương trình hoàn chỉnh nằm ở mục 8.

**NewString** cho phép giữ nguyên ký tự U+0000 vì độ dài được truyền tường minh. Nó cũng giữ đúng cặp surrogate UTF-16, khác với cách xử lý một buffer byte UTF-8 chuẩn. JNI không mặc định rằng **jchar*** là chuỗi C null-terminated.

Nếu **len = 0**, có thể tạo chuỗi rỗng theo hợp đồng. Nếu không đủ bộ nhớ, hàm trả **NULL** và có thể phát sinh **OutOfMemoryError**; không tiếp tục dùng reference NULL.

### 3.2. NewStringUTF: đầu vào MUTF-8

Chữ ký:

~~~c
jstring NewStringUTF(JNIEnv *env, const char *bytes);
~~~

Ví dụ an toàn với ASCII (ngoại trừ U+0000, ASCII thông thường tương thích MUTF-8):

~~~c
jstring message = (*env)->NewStringUTF(env, "JNI ASCII");
if (message == NULL) {
    return; // Kiểm tra lỗi cấp phát trước khi dùng.
}
~~~

**NewStringUTF** tìm dấu kết thúc chuỗi C (byte 00); con trỏ input phải trỏ đến dãy MUTF-8 hợp lệ, có terminator. Ví dụ **"JNI ASCII"** tương thích. Trái lại, chuỗi byte UTF-8 chuẩn mang emoji sẽ chứa một chuỗi 4 byte mà MUTF-8 không mã hóa theo cách đó.

Không dùng **NewStringUTF** để nhận payload nhị phân. Một byte 00 trong dữ liệu sẽ kết thúc input, còn các byte không phải MUTF-8 hợp lệ có thể gây hành vi không mong muốn. Đối với byte[] hoặc protocol payload, giữ nó ở dạng byte[]/buffer với độ dài tường minh.

### 3.3. Cấp phát và ownership sau khi tạo

Cả NewString và NewStringUTF trả về **jstring**, tức một **local Java reference** khi được gọi từ JNI thông thường. JVM quản lý nội dung String; **không free(jstring)** và không giả định chuỗi là malloc buffer.

- Trả trực tiếp local jstring từ native method là hợp lệ; JVM chuyển reference về phía Java.
- Nếu tạo nhiều local references trong vòng lặp native dài, dùng **DeleteLocalRef** hoặc **PushLocalFrame/PopLocalFrame** theo đúng cách để tránh tích lũy.
- Nếu giữ reference sau khi native method trả về hoặc qua native thread khác, phải dùng reference có vòng đời phù hợp, ví dụ **NewGlobalRef** và xóa bằng **DeleteGlobalRef** lúc không còn dùng.
- Xóa local reference chỉ xóa handle tạm JNI; nếu Java còn giữ đối tượng String thì dữ liệu không bị mất.

**Lưu ý:** Java String bất biến (immutable). Các thao tác JNI kể trên tạo/đọc String, không biến jstring thành một vùng có thể ghi tùy tiện từ C.

## 4. Đọc chiều dài: code units, code points và byte

### 4.1. GetStringLength

~~~c
jsize units = (*env)->GetStringLength(env, input);
~~~

Giá trị này tương ứng với **input.length()** trong Java: số đơn vị UTF-16. Nếu Java String chứa một emoji ngoài BMP thì emoji đó chiếm 2. Cơ chế này **không** duyệt grapheme cluster; một ký tự người dùng nhìn thấy cũng có thể gồm nhiều code points kết hợp.

Ví dụ Java độc lập:

~~~java
import java.nio.charset.StandardCharsets;

public final class StringLengthUnits {
    public static void main(String[] args) {
        String value = "A" + (char) 0 + (char) 0x00E9
                + new String(Character.toChars(0x1F642));

        System.out.println("utf16=" + value.length());
        System.out.println(
                "codePoints=" + value.codePointCount(0, value.length())
        );
        System.out.println(
                "standardUtf8Bytes="
                        + value.getBytes(StandardCharsets.UTF_8).length
        );
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac StringLengthUnits.java
java StringLengthUnits
~~~

**Stdout chính xác:**

~~~text
utf16=5
codePoints=4
standardUtf8Bytes=8
~~~

Chương trình này **chỉ dùng Java** để làm rõ ba đơn vị; nó không đòi hỏi thư viện native. Kết quả **GetStringLength** tương ứng sẽ là **5** khi truyền cùng String vào JNI.

### 4.2. GetStringUTFLength và giới hạn của jsize

~~~c
jsize bytes = (*env)->GetStringUTFLength(env, input);
~~~

Hàm trả về số byte theo **modified UTF-8** (không tính byte NUL terminator). Nó không phải số byte UTF-8 chuẩn, không phải String.length và cũng không phải số code points.

**Cảnh báo cho dữ liệu lớn:** Từ **JDK 24**, **GetStringUTFLength** bị deprecated vì trả jsize 32 bit. Nếu biểu diễn MUTF-8 dài hơn khả năng của jsize, tài liệu JNI hiện hành quy định hàm cũ chỉ trả số byte tới ký tự cuối cùng còn biểu diễn trọn vẹn trong giới hạn đó; vì vậy kết quả có thể **thiếu**, không được dùng để cấp phát buffer toàn bộ chuỗi lớn.

Hàm thay thế trên JDK 24+:

~~~c
jlong bytes = (*env)->GetStringUTFLengthAsLong(env, input);
~~~

**GetStringUTFLengthAsLong không có trong JDK 17–23.** Không chèn nó vào một native library được build bằng JNI headers của JDK 17 rồi tuyên bố chương trình vẫn biên dịch trên JDK 17. Khi cần hỗ trợ JDK 17 và chuỗi cực lớn, có thể:

- Cấu hình giới hạn đầu vào nhỏ để phép nhân **3 × số code units** vẫn không vượt INT_MAX, như ví dụ đầy đủ bên dưới.
- Hoặc xử lý theo đoạn với buffer giới hạn, cộng số byte trong kiểu **jlong**/**size_t** bằng thuật toán encoding được kiểm chứng.
- Hoặc không chuyển cả chuỗi sang MUTF-8 ngay từ đầu: thực hiện công việc theo UTF-16 regions hoặc dùng luồng byte được encode chuẩn.

### 4.3. So sánh API trong từng môi trường

| Cần đo | Java | JNI |
| --- | --- | --- |
| Đơn vị UTF-16 | **s.length()** | **GetStringLength** |
| Unicode code points | **s.codePointCount(0, s.length())** | Tự duyệt code units đúng quy tắc surrogate hoặc xử lý phía Java |
| Byte UTF-8 chuẩn | **s.getBytes(UTF_8).length** cho chuỗi nhỏ, hoặc encoder/stream có giới hạn | Chuyển encoding rõ ràng rồi đo byte; không lấy GetStringUTFLength thay |
| Byte modified UTF-8 | Không phải kết quả của StandardCharsets.UTF_8 | **GetStringUTFLengthAsLong** (JDK 24+); **GetStringUTFLength** cho dữ liệu nhỏ đã giới hạn |

Chỉ số byte sẽ thay đổi theo encoding. Không đo byte bằng **strlen** trên jchar*; đó là con trỏ 16 bit. Ngay cả với char* của một API JNI, chỉ dùng phép đo C-string khi đã có bảo đảm hợp đồng về encoding, terminator và kích thước buffer.

## 5. Đọc nội dung String: mượn dữ liệu hay sao chép theo vùng?

### 5.1. GetStringChars / ReleaseStringChars (UTF-16)

~~~c
const jchar *chars = (*env)->GetStringChars(env, input, NULL);
if (chars == NULL) {
    return; // Có thể đã có pending OutOfMemoryError.
}

jsize units = (*env)->GetStringLength(env, input);
for (jsize i = 0; i < units; i++) {
    // Đọc chars[i] như một UTF-16 code unit.
}

(*env)->ReleaseStringChars(env, input, chars);
~~~

Đây là snippet, áp dụng khi input hợp lệ. Không dùng **strlen(chars)**: mỗi jchar dài 16 bit và dãy chưa chắc có NUL terminator. **isCopy** của GetStringChars có thể được truyền để biết JVM đang trả copy hay view, nhưng **không thay đổi quy tắc release**.

Vì JVM có thể sao chép, việc gọi GetStringChars cho chuỗi cực lớn có thể tạo ra một buffer lớn tạm thời. Hãy đánh giá nhu cầu thực tế thay vì xem API là zero-copy.

### 5.2. GetStringUTFChars / ReleaseStringUTFChars (MUTF-8)

~~~c
const char *bytes = (*env)->GetStringUTFChars(env, input, NULL);
if (bytes == NULL) {
    return;
}

/* Xử lý bytes theo hợp đồng modified UTF-8 của JNI. */

(*env)->ReleaseStringUTFChars(env, input, bytes);
~~~

**GetStringUTFChars** cung cấp dữ liệu MUTF-8, không tự động biến nó thành UTF-8 chuẩn. Nếu cần byte để gửi HTTP/file/protocol sử dụng UTF-8 chuẩn, hãy encode đúng chuẩn đó. Con trỏ lấy từ JNI chỉ có hiệu lực theo hợp đồng tới khi gọi ReleaseStringUTFChars; không giữ pointer cho thread khác hoặc sử dụng sau release.

JNI specification không yêu cầu mọi vùng được trả về từ string access APIs đều có terminator; hãy dùng chiều dài được xác định rõ thay vì tùy tiện gọi **strlen** hoặc đọc vượt phạm vi.

### 5.3. GetStringRegion: đọc từng đoạn UTF-16

Hàm:

~~~c
void GetStringRegion(
    JNIEnv *env, jstring str, jsize start, jsize len, jchar *buffer
);
~~~

Trong đó **start và len đều tính bằng UTF-16 code units**. JNI copy vào buffer do native code cấp; không cần lấy một bản sao toàn chuỗi rồi giữ lâu.

Ví dụ đọc tối đa 1.024 code units mỗi lần:

~~~c
enum { CHUNK = 1024 };
jchar buffer[CHUNK];

jsize total = (*env)->GetStringLength(env, input);
for (jsize offset = 0; offset < total; ) {
    jsize remaining = total - offset;
    jsize take = remaining < CHUNK ? remaining : CHUNK;

    (*env)->GetStringRegion(env, input, offset, take, buffer);
    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    for (jsize i = 0; i < take; ++i) {
        /* Xử lý buffer[i], chỉ trong phạm vi [0, take). */
    }
    offset += take;
}
~~~

Đây là đoạn minh họa nằm trong native method void với input hợp lệ, không phải một chương trình độc lập. Dùng **total - offset** trước khi cộng để hạn chế tràn chỉ số; buffer trên stack chỉ chiếm **1.024 × sizeof(jchar)** byte và luôn đủ chỗ cho số phần tử được yêu cầu.

**Cẩn thận với surrogate pair ở biên đoạn.** Nếu thuật toán muốn tính Unicode code points chứ không phải đơn vị UTF-16, một high surrogate có thể nằm ở cuối đoạn, còn low surrogate nằm ở đầu đoạn kế tiếp. Cần lưu trạng thái giữa hai đoạn hoặc xử lý theo logic code point đúng quy tắc.

### 5.4. GetStringUTFRegion: tham số là ký tự UTF-16, output là byte MUTF-8

Hàm:

~~~c
void GetStringUTFRegion(
    JNIEnv *env, jstring str, jsize start, jsize len, char *buffer
);
~~~

**Sai lầm rất nguy hiểm:** cấp phát buffer đúng bằng **len** byte rồi gọi GetStringUTFRegion. **len** là số UTF-16 code units, còn output MUTF-8 có thể lên tới **3 byte cho mỗi code unit**. Với một đoạn dài **k** code units, cần buffer đủ cho tối đa **3k byte**, và thêm **1 byte** nếu chương trình muốn tự đặt dấu kết thúc C-string. Trước khi nhân/cộng kích thước, phải chống integer overflow.

Ví dụ với đoạn tối đa 1.024 code units (không tạo chuỗi MUTF-8 toàn phần):

~~~c
#include <string.h>

/* Snippet trong native method, input là jstring hợp lệ. */
enum { CHUNK = 1024 };
char bytes[3 * CHUNK + 1];

jsize total = (*env)->GetStringLength(env, input);
for (jsize offset = 0; offset < total; ) {
    jsize remaining = total - offset;
    jsize take = remaining < CHUNK ? remaining : CHUNK;

    /*
     * Buffer được xóa để luôn có byte 00 sau vùng dữ liệu MUTF-8.
     * Input MUTF-8 hợp lệ không chứa byte 00 ở giữa.
     */
    memset(bytes, 0, sizeof(bytes));
    (*env)->GetStringUTFRegion(env, input, offset, take, bytes);
    if ((*env)->ExceptionCheck(env)) {
        return;
    }

    size_t encodedBytes = strlen(bytes);
    /* encodedBytes <= 3 * take. Dùng ngay rồi tiếp tục đoạn sau. */
    (void)encodedBytes;
    offset += take;
}
~~~

Cách trên dùng buffer kích thước cố định, tự xóa để đặt terminator an toàn theo hướng dẫn trong JNI spec. Vì MUTF-8 không chứa byte 00 bên trong nội dung, strlen sau bước chuẩn bị buffer có thể đo phần đã encode. **Không** áp dụng mô hình này cho byte dữ liệu tùy ý hoặc UTF-8 chuẩn có ký tự U+0000 bên trong, vì những byte đó có thể chứa 00 thật.

Nếu xử lý stream ở mức Unicode code point, không ghép các đoạn UTF-8 chuẩn bằng cách mã hóa riêng từng nửa surrogate; phải giữ state hoặc dùng bộ mã hóa có xử lý ranh giới chuẩn.

## 6. Dữ liệu lớn: thiết kế theo luồng, giới hạn và vòng đời

### 6.1. Tránh sao chép toàn chuỗi khi không cần

Nếu mục tiêu chỉ là tìm ký tự ASCII, đếm dấu phân cách, tính checksum hoặc kiểm tra một điều kiện đơn giản, không nhất thiết phải gọi GetStringUTFChars để tạo MUTF-8 cho toàn bộ String. Có thể dùng **GetStringRegion** để xử lý từng khối nhỏ, giữ bộ nhớ tạm ở mức **O(chunk size)**.

Với n code units và kích thước khối k:

- Bộ nhớ native bổ sung cho một lần đọc region: **O(k)**.
- Số lần gọi JNI region: xấp xỉ **ceil(n/k)**.
- Tổng công việc quét: **O(n)**, chưa tính chuyển đổi/mã hóa nếu có.

k quá nhỏ làm tăng chi phí JNI crossing. k quá lớn tăng stack/heap buffer và có thể ảnh hưởng cache; nên đo trên workload mục tiêu. Một khối **4.096 jchar** thường là điểm bắt đầu dễ giải thích, **không phải thông số tối ưu phổ quát**.

### 6.2. Giới hạn độ dài byte và kiểm tra số học

**jsize** dùng cho Java String/array length (32 bit có dấu); còn byte encoded MUTF-8 có thể lớn tới khoảng 3 lần số code units. Đừng viết:

~~~c
/* KHÔNG AN TOÀN nếu n lớn: phép nhân có thể tràn. */
jsize bytesNeeded = 3 * n + 1;
char *buffer = malloc((size_t)bytesNeeded);
~~~

Đây là ví dụ **cố ý sai**, không dùng thực tế. Trong code sản xuất có phép nhân/cộng động, kiểm tra với **SIZE_MAX**, chính sách giới hạn bộ nhớ và kiểu **size_t** trước khi cấp phát. Ví dụ mẫu kiểm tra:

~~~c
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>

static char *allocate_mutf8_capacity(size_t units) {
    if (units > (SIZE_MAX - 1u) / 3u) {
        return NULL;
    }
    size_t bytes = units * 3u + 1u;
    return malloc(bytes);
}
~~~

Hàm trên chỉ minh họa **kiểm tra overflow**, chưa phải cơ chế cấp phát production: vẫn cần quota ứng dụng, xử lý malloc thất bại, free đúng nơi, và phân biệt bộ đệm encoded với String gốc. Không nên cấp phát một vùng vài gigabyte chỉ vì phép nhân không tràn.

### 6.3. GetStringCritical chỉ dành cho đoạn thật ngắn

**GetStringCritical / ReleaseStringCritical** có thể cho JVM cơ hội tránh một số copy, nhưng **không bảo đảm zero-copy**. Trong khoảng giữa hai lệnh, mã native **không được gọi JNI API tùy ý hoặc thực hiện thao tác có thể block**, vì JVM có thể cần hạn chế GC/di chuyển đối tượng.

Không giữ critical pointer trong khi:

- Đọc/ghi file hoặc chờ network.
- Gọi JNI method, cấp phát Java objects hoặc thực hiện callback.
- Đợi mutex/condition của thread khác hay làm tính toán kéo dài.
- Truyền pointer sang một asynchronous task.

Đối với bài toán quét chuỗi lớn, **GetStringRegion** thường là lựa chọn rõ ràng hơn khi muốn quản lý bộ nhớ tạm và tránh giữ critical region dài. Chỉ tối ưu bằng GetStringCritical khi có benchmark và hiểu rõ các điều kiện JNI.

### 6.4. Khi dữ liệu thực chất là byte stream

Không phải payload lớn nào cũng nên chuyển thành Java String:

| Dữ liệu | Hình thức phù hợp |
| --- | --- |
| Văn bản Unicode đã decode và cần xử lý code units | **String / GetStringRegion** |
| Văn bản cần xuất file/API theo UTF-8 chuẩn | **CharsetEncoder / String.getBytes(UTF_8)** khi phù hợp, hoặc encode theo từng đoạn |
| Binary, nén, ảnh, protocol frame | **byte[]**, stream hoặc ByteBuffer; giữ nguyên byte và độ dài |
| Buffer lớn trao đổi qua native nhiều lần | Cân nhắc **DirectByteBuffer** và hợp đồng ownership/lifetime, đo chi phí và kiểm tra bounds |

Với một **jbyteArray**, JNI dùng **GetArrayLength**, **GetByteArrayRegion** và **SetByteArrayRegion** khi muốn thao tác theo từng đoạn; dữ liệu byte không tự mang thông tin charset. Nếu chọn **DirectByteBuffer**, cần quản lý rõ vòng đời bộ nhớ native, giới hạn dung lượng và vị trí đọc/ghi; đây là một lựa chọn thiết kế riêng, không phải lý do để ép chuỗi Unicode thành byte tùy ý.

Đối với text input từ mạng/file, nên xác định **encoding, chính sách lỗi decode/encode, kích thước tối đa, cách xử lý surrogate lỗi và thời điểm normalize nếu có yêu cầu**. Các tính chất này không do JNI quyết định hộ ứng dụng.

## 7. Bẫy Unicode khi chia đoạn

### 7.1. UTF-16 code units khác Unicode code points

Một thuật toán kiểm tra “số ký tự” có thể đòi hỏi một trong ba khái niệm:

- **UTF-16 code units:** hợp đồng của Java String.length, GetStringLength và vị trí/độ dài của GetStringRegion.
- **Unicode code points:** một đơn vị Unicode có thể chiếm một hoặc hai UTF-16 code units; ví dụ emoji.
- **Grapheme clusters:** ký tự người dùng cảm nhận; có thể gồm nhiều code points, dấu tổ hợp, emoji nối bằng zero-width joiner. Cần một thuật toán segmentation riêng.

Không tự gọi **GetStringLength** rồi gắn nhãn “số ký tự người dùng nhìn thấy”. JNI không tự tách grapheme cluster.

### 7.2. Chia code units đúng khi chỉ đếm ASCII

Nếu bài toán chỉ đếm UTF-16 code unit bằng U+0041 (**A**), chia tại bất kỳ ranh giới jchar nào vẫn cho kết quả đúng: chữ A không phải một nửa surrogate. Ví dụ đầy đủ ở mục 8 dùng thao tác đó.

Nhưng nếu cần đọc từng code point:

1. Khi gặp high surrogate ở cuối khối, lưu lại chờ khối sau.
2. Nếu khối sau bắt đầu bằng low surrogate, ghép thành code point tương ứng.
3. Nếu không có low surrogate hợp lệ, xử lý theo chính sách lỗi/đại diện đã xác định.
4. Không đếm mỗi nửa surrogate là một emoji riêng.

Nếu muốn tạo **UTF-8 chuẩn**, hai nửa surrogate phải được xử lý thống nhất. **GetStringUTFRegion** tạo **modified UTF-8**, trong đó hai code units surrogate vốn được mã hóa riêng, nên kết quả vẫn khác chuẩn UTF-8.

### 7.3. Embedded NUL là một phép kiểm tra quan trọng

Một Java String có thể chứa U+0000 ở giữa, ví dụ **"A" + (char) 0 + "B"**, và length là 3. Nếu chuyển thành một byte array UTF-8 chuẩn, dãy byte có thể là **41 00 42**. Dùng **strlen** trên dãy byte này cho kết quả 1, không phải 3.

Trái lại, MUTF-8 biểu diễn U+0000 thành **C0 80**; nếu cần gửi dữ liệu ra hệ thống chuẩn UTF-8, phải chuyển encoding và truyền **byte length tường minh**, không dựa vào terminator kiểu C.

## 8. Ví dụ chạy độc lập: Java 17+ kết hợp C/JNI

Chương trình demo ba nhóm API:

- **NewString** tạo chuỗi gồm **A, U+0000, é, 🙂** từ jchar[].
- **NewStringUTF** tạo String ASCII.
- **GetStringLength / GetStringUTFLength** đo code units và **byte modified UTF-8** của một chuỗi nhỏ đã giới hạn.
- **GetStringRegion** xử lý **1.000.001 UTF-16 code units** theo khối 4.096 mà không tạo bản sao toàn chuỗi sang native buffer.

Để chương trình chạy đúng trên **JDK 17+**, phần C **không gọi GetStringUTFLengthAsLong**, vì hàm đó chỉ có từ JDK 24. Thay vào đó, method nativeLengths giới hạn đầu vào ở **1.000.000 UTF-16 code units** trước khi dùng GetStringUTFLength; ngay cả trường hợp xấu nhất (3 byte/code unit), kết quả vẫn trong phạm vi jsize.

### Bước 1 — Tạo JniStringMetrics.java

~~~java
import java.nio.charset.StandardCharsets;

public final class JniStringMetrics {
    static {
        System.loadLibrary("jnistringmetrics");
    }

    private JniStringMetrics() {
    }

    private static native String nativeFromUtf16();

    private static native String nativeFromAscii();

    // Chỉ dùng cho chuỗi nhỏ, giới hạn được kiểm tra ở native side.
    private static native long[] nativeLengths(String value);

    // Quét chuỗi theo khối, không copy toàn bộ String qua C.
    private static native long nativeCountAsciiA(String value);

    public static void main(String[] args) {
        String mixed = nativeFromUtf16();
        long[] lengths = nativeLengths(mixed);

        System.out.println("ascii=" + nativeFromAscii());
        System.out.println("utf16Units=" + lengths[0]);
        System.out.println(
                "codePoints=" + mixed.codePointCount(0, mixed.length())
        );
        System.out.println(
                "standardUtf8Bytes="
                        + mixed.getBytes(StandardCharsets.UTF_8).length
        );
        System.out.println("modifiedUtf8Bytes=" + lengths[1]);

        String large = "A".repeat(1_000_000) + "\u00E9";
        System.out.println("largeUtf16Units=" + large.length());
        System.out.println("countA=" + nativeCountAsciiA(large));
    }
}
~~~

Trong Java, String **mixed** là kết quả của **NewString** từ native code. Phần chuẩn **StandardCharsets.UTF_8** chỉ dùng để đo UTF-8 chuẩn; modified UTF-8 được đo bằng JNI. Chuỗi **large** có một triệu chữ A và một chữ é; nó chứa **1.000.001 UTF-16 code units**.

### Bước 2 — Biên dịch và sinh JNI header

~~~bash
javac -h . JniStringMetrics.java
~~~

Lệnh tạo **JniStringMetrics.class** và **JniStringMetrics.h**. Để tránh sai JNI symbol name và signature, dùng header do chính **javac -h** sinh ở cùng phiên bản source. Các native method đều là **static**, vì thế JNI entry points nhận **JNIEnv \*** và **jclass** làm hai đối số đầu.

### Bước 3 — Tạo jni_string_metrics.c

~~~c
#include "JniStringMetrics.h"

#define CHUNK 4096
#define MAX_SMALL_UNITS 1000000

/* Phát Java exception có kiểm soát; không nuốt lỗi cũ. */
static void throw_by_name(
        JNIEnv *env, const char *class_name, const char *message) {
    jclass exception_class = (*env)->FindClass(env, class_name);
    if (exception_class == NULL) {
        return; /* FindClass đã có pending exception. */
    }
    (*env)->ThrowNew(env, exception_class, message);
    (*env)->DeleteLocalRef(env, exception_class);
}

/* UTF-16: len là số jchar, U+0000 không cắt chuỗi. */
JNIEXPORT jstring JNICALL
Java_JniStringMetrics_nativeFromUtf16(JNIEnv *env, jclass cls) {
    const jchar units[5] = {
        0x0041, 0x0000, 0x00E9, 0xD83D, 0xDE42
    };
    (void)cls;
    return (*env)->NewString(env, units, 5);
}

/* NewStringUTF nhận MUTF-8; ASCII thường là đầu vào hợp lệ. */
JNIEXPORT jstring JNICALL
Java_JniStringMetrics_nativeFromAscii(JNIEnv *env, jclass cls) {
    (void)cls;
    return (*env)->NewStringUTF(env, "JNI ASCII");
}

/* Chỉ đo MUTF-8 bằng GetStringUTFLength khi input đã được giới hạn. */
JNIEXPORT jlongArray JNICALL
Java_JniStringMetrics_nativeLengths(
        JNIEnv *env, jclass cls, jstring value) {
    (void)cls;

    if (value == NULL) {
        throw_by_name(env, "java/lang/NullPointerException",
                      "value must not be null");
        return NULL;
    }

    jsize units = (*env)->GetStringLength(env, value);
    if (units > MAX_SMALL_UNITS) {
        throw_by_name(env, "java/lang/IllegalArgumentException",
                      "nativeLengths accepts at most 1000000 UTF-16 units");
        return NULL;
    }

    /* Tối đa 3 * 1000000 byte nên không tràn jsize. */
    jsize bytes = (*env)->GetStringUTFLength(env, value);
    jlong metrics[2] = {(jlong)units, (jlong)bytes};

    jlongArray result = (*env)->NewLongArray(env, 2);
    if (result == NULL) {
        return NULL; /* Có thể OutOfMemoryError. */
    }

    (*env)->SetLongArrayRegion(env, result, 0, 2, metrics);
    if ((*env)->ExceptionCheck(env)) {
        return NULL;
    }
    return result;
}

/* Đếm UTF-16 code units tương ứng chữ A trên dữ liệu lớn. */
JNIEXPORT jlong JNICALL
Java_JniStringMetrics_nativeCountAsciiA(
        JNIEnv *env, jclass cls, jstring value) {
    (void)cls;

    if (value == NULL) {
        throw_by_name(env, "java/lang/NullPointerException",
                      "value must not be null");
        return 0;
    }

    jsize total = (*env)->GetStringLength(env, value);
    jchar buffer[CHUNK];
    jlong count = 0;

    for (jsize offset = 0; offset < total; ) {
        jsize remaining = total - offset;
        jsize take = remaining < CHUNK ? remaining : CHUNK;

        (*env)->GetStringRegion(env, value, offset, take, buffer);
        if ((*env)->ExceptionCheck(env)) {
            return 0; /* Exception truyền về Java. */
        }

        for (jsize i = 0; i < take; i++) {
            if (buffer[i] == (jchar)0x0041) {
                count++;
            }
        }
        offset += take;
    }
    return count;
}
~~~

**Các điểm cần kiểm tra trong native code:**

1. **NewString** nhận đúng **5 jchar**; ký tự U+0000 ở giữa không làm chuỗi bị rút ngắn.
2. **NewStringUTF** chỉ nhận dãy ASCII hợp lệ, không nhầm UTF-8 chuẩn tùy ý với MUTF-8.
3. **nativeLengths** bảo vệ API độ dài byte kiểu jsize bằng một giới hạn rõ ràng. Nó trả **long[2]** để Java dễ hiển thị; nếu cần làm việc với MUTF-8 thực sự lớn trên JDK 24+, dùng **GetStringUTFLengthAsLong** trong nhánh biên dịch phù hợp.
4. **nativeCountAsciiA** cấp buffer cố định **4.096 jchar** trên stack, duyệt từng vùng và cộng vào **jlong**; nó không cấp phát buffer tăng theo chiều dài toàn chuỗi.
5. Sau **GetStringRegion**, code gọi **ExceptionCheck** để dừng khi thao tác JNI bị lỗi; không tiếp tục đọc một buffer có thể chưa được điền hợp lệ.
6. Lệnh **ThrowNew** truyền lỗi về Java; phần native trả về giá trị chỉ để hoàn tất hàm C và không phải một kết quả thành công khi đang có pending exception.
7. Không có code giữ pointer vào dữ liệu String sau khi JNI call kết thúc, không có unbalanced Get/Release và không có critical region giữ lâu.
8. Code demo đếm **U+0041** chính xác trong UTF-16; đây không phải bộ đếm grapheme cluster hay bộ chuyển đổi UTF-8.

### Bước 4 — Build thư viện native

Đảm bảo **JAVA_HOME** trỏ tới JDK có header **jni.h** và compiler tạo đúng OS/CPU/ABI với JVM chạy chương trình.

**Linux (GCC):**

~~~bash
gcc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  jni_string_metrics.c -o libjnistringmetrics.so
~~~

**macOS (Clang):**

~~~bash
clang -std=c11 -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  jni_string_metrics.c -o libjnistringmetrics.dylib
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" jni_string_metrics.c /link /OUT:jnistringmetrics.dll
~~~

Ba lệnh là các phương án thay thế theo hệ điều hành, không phải ba bước cùng chạy. Chúng giả định compiler và **JAVA_HOME** được cấu hình hợp lệ. Nếu bị lỗi nạp DLL/SO/dylib, kiểm tra **java.library.path**, dependency native, architecture và libc/runtime trước khi nghi ngờ phép đo độ dài.

### Bước 5 — Chạy Java

Trong thư mục có class và thư viện vừa biên dịch:

~~~bash
java -Djava.library.path=. JniStringMetrics
~~~

**Stdout chính xác nếu build và load thành công:**

~~~text
ascii=JNI ASCII
utf16Units=5
codePoints=4
standardUtf8Bytes=8
modifiedUtf8Bytes=11
largeUtf16Units=1000001
countA=1000000
~~~

Nếu chạy trên **JDK 24+** có hạn chế native access và adapter nằm trên classpath, có thể cần cho phép quyền native access rõ ràng:

~~~bash
java --enable-native-access=ALL-UNNAMED -Djava.library.path=. JniStringMetrics
~~~

Trên JDK khác nhau, thiếu native access permission có thể dẫn tới cảnh báo trên **stderr** hoặc bị từ chối theo cấu hình; những dòng đó không thuộc **stdout** mẫu. Tùy chọn quyền được khai báo theo module khi ứng dụng modularized.

### Bước 6 — Đọc kết quả theo đơn vị

- **utf16Units=5**: NewString đã tạo **5 UTF-16 code units**; khớp Java String.length và GetStringLength.
- **codePoints=4**: một emoji ngoài BMP dùng 2 code units nhưng 1 code point.
- **standardUtf8Bytes=8**: UTF-8 chuẩn mã hóa U+0000 thành 1 byte và 🙂 thành 4 byte.
- **modifiedUtf8Bytes=11**: JNI MUTF-8 mã hóa U+0000 thành 2 byte và cặp surrogate của 🙂 thành 6 byte.
- **largeUtf16Units=1000001**: Java tạo 1.000.000 chữ A và một chữ é.
- **countA=1000000**: native method đi qua toàn chuỗi theo các khối 4.096 jchar và đếm đúng số chữ A, không đọc phần tử vượt buffer.

## 9. Những lựa chọn xử lý khi dữ liệu thật sự rất lớn

### Tình huống A — Native code chỉ cần phân tích text

Ví dụ: đếm ký tự ASCII, tìm dấu phân cách, tính hash ở mức UTF-16 hoặc phân tích cấu trúc văn bản đã decode.

**Ưu tiên:** GetStringRegion theo khối và thuật toán giữ state tối thiểu. Kiểm tra ranh giới surrogate nếu thuật toán làm việc với code point. Không buộc toàn String thành một MUTF-8 char* chỉ để duyệt.

### Tình huống B — Native code giao tiếp với một thư viện yêu cầu UTF-8 chuẩn

Ví dụ: C API của thư viện JSON yêu cầu **UTF-8 chuẩn + byte length**.

**Ưu tiên:** xác định một bước chuyển encoding rõ ràng, cung cấp đúng byte length, truyền byte[]/buffer hoặc stream. Không dùng **GetStringUTFChars** và mặc định byte mà nó trả về là standard UTF-8.

Nếu cần tương thích với C API nhận null-terminated string, phải có chính sách cho **U+0000** trong nội dung, vì UTF-8 chuẩn có byte 00 thật và có thể làm C API đọc thiếu dữ liệu. Nên chọn API cho phép truyền buffer kèm độ dài.

### Tình huống C — Native code tạo văn bản Unicode lớn

Không nhất thiết phải tạo một char* MUTF-8 khổng lồ rồi gọi NewStringUTF. Có thể:

- Tạo từng phần ở mức Java với **StringBuilder**, giới hạn kích thước kết quả; hoặc chuyển các đoạn UTF-16 bằng API có độ dài tường minh.
- Nếu cần tạo một String duy nhất, hiểu rằng String Java phải chứa toàn bộ nội dung và có giới hạn độ dài cùng chi phí bộ nhớ riêng.
- Khi dữ liệu là một stream chưa cần materialize thành String, giữ nó là stream/buffer và tiêu thụ từng đoạn.

Để tăng throughput, đo chi phí JNI crossing, số bản sao dữ liệu, latency, native RSS, Java heap và GC. **GetStringCritical** không phải mặc định tốt nhất; chỉ dùng khi đoạn critical ngắn và đã kiểm chứng lợi ích.

### Tình huống D — Đầu vào không đáng tin hoặc có kích thước bất thường

Áp dụng kiểm tra ở ranh giới Java/native: giới hạn tối đa, kiểm tra phép tính byte capacity, rõ charset, xử lý malformed input, và từ chối payload vượt quota. Với buffer nhận từ native code, chỉ dùng **NewString** nếu đúng UTF-16 code units và kích thước hợp lệ; chỉ dùng **NewStringUTF** nếu byte là MUTF-8 hợp lệ có C terminator.

## 10. Các lỗi thường gặp và cách khắc phục

| Lỗi | Vì sao sai | Cách đúng |
| --- | --- | --- |
| “GetStringLength là số Unicode characters người dùng thấy” | JNI đếm UTF-16 code units; emoji và grapheme có thể nhiều units | Phân biệt code units, code points, grapheme clusters |
| Dùng GetStringUTFLength để đo UTF-8 chuẩn | API tính **modified UTF-8**, có quy tắc khác cho U+0000 và supplementary | Encode chuẩn bằng UTF-8/CharsetEncoder rồi đo byte |
| Dùng GetStringUTFLength với chuỗi cực lớn | jsize không chứa được mọi byte length | JDK 24+: GetStringUTFLengthAsLong; hoặc chunking/cap |
| Truyền byte UTF-8 có emoji vào NewStringUTF | 4-byte UTF-8 chuẩn không phải cách mã hóa MUTF-8 | Convert encoding hoặc dùng NewString từ UTF-16 |
| Truyền buffer có byte 00 nội dung vào NewStringUTF | Byte 00 kết thúc C-string | Dùng API length-aware và encoding đúng |
| Gọi strlen trên jchar* | jchar là 16 bit, không phải C char string | Dùng GetStringLength và truy cập theo chỉ số |
| Cấp buffer len byte cho GetStringUTFRegion | len tính code units nhưng output có thể 3× len byte | Cấp tối đa 3×len (cộng terminator nếu cần), kiểm tra overflow |
| Giả định vùng GetStringUTFRegion đã NUL-terminated | Spec không bảo đảm terminator | Dùng byte length rõ ràng hoặc tự xóa/đặt terminator an toàn |
| Quên ReleaseStringChars/UTFChars | Giữ tài nguyên/pin/copy quá lâu | Ghép chính xác Get với Release trên mọi nhánh |
| Free dữ liệu do GetStringChars trả | Vùng nhớ thuộc hợp đồng JNI, không phải malloc tự sở hữu | ReleaseStringChars, không free |
| Duyệt hết một String lớn qua GetStringUTFChars không cân nhắc | Có thể tạo bản sao lớn trong native memory | Ưu tiên region theo chunk khi phù hợp |
| Chia chunk đúng giữa hai surrogate nhưng xử lý từng đoạn là code points độc lập | Tách một code point thành hai nửa | Giữ trạng thái high surrogate qua ranh giới |
| Giữ GetStringCritical trong khi I/O hoặc callback | Có thể cản JVM/GC và vi phạm restricted region | Giữ critical region thật ngắn hoặc dùng regions |
| Dùng size int tính 3×length+1 | Có thể overflow trước malloc | Kiểm tra với size_t/SIZE_MAX và quota |
| Biến binary thành String không biết charset | Mất hoặc biến đổi byte dữ liệu | Dùng byte[]/ByteBuffer; decode rõ charset khi cần |
| Gọi JNI API tiếp khi có pending exception | Vi phạm hợp đồng ở nhiều lời gọi tiếp theo | Dừng, cleanup API được phép, trả exception về Java |

## 11. Checklist áp dụng trước production

- [ ] Ghi rõ đơn vị đang đo: **UTF-16 code units**, **Unicode code points**, **grapheme clusters**, **UTF-8 bytes** hay **MUTF-8 bytes**.
- [ ] Dùng **NewString** với jchar[]/UTF-16 có độ dài; **NewStringUTF** chỉ với modified UTF-8 hợp lệ.
- [ ] Có test cho U+0000, ký tự BMP nhiều byte, supplementary Unicode và input rỗng.
- [ ] Với JNI strings, dùng đúng Get/Release pair và không giữ pointer quá vòng đời.
- [ ] Kiểm tra NULL sau API có thể lỗi; không tiếp tục JNI call thông thường khi có pending exception.
- [ ] Với GetStringUTFRegion, chứng minh **buffer byte capacity** đủ, có kiểm tra overflow và terminator khi cần.
- [ ] Với String lớn, cân nhắc region/chunk hoặc stream; tránh bản sao toàn chuỗi không cần thiết.
- [ ] Nếu cần byte length MUTF-8 lớn, ưu tiên **GetStringUTFLengthAsLong trên JDK 24+**; không coi GetStringUTFLength cũ là nguồn số byte đầy đủ vô điều kiện.
- [ ] Với dữ liệu network/file, dùng UTF-8 chuẩn hoặc charset quy định rõ, không trộn với MUTF-8 của JNI.
- [ ] Nếu phải xử lý Unicode code points, duy trì state của surrogate pairs qua ranh giới khối.
- [ ] Đã benchmark batch size, thời gian copy/encode, CPU, heap, native memory và p95 latency trong workload thật.
- [ ] Đã kiểm thử với binary và JDK mục tiêu; dùng **-Xcheck:jni** trong môi trường kiểm thử phù hợp.
- [ ] Ghi rõ giới hạn kích thước và hành vi khi vượt giới hạn, không xử lý cấp phát vô hạn.

## 12. Câu hỏi tự kiểm tra

**1. Một String Java gồm một emoji ngoài BMP có length bằng 2. JNI GetStringLength trả về bao nhiêu?**

**Trả lời:** 2, vì emoji đó chiếm hai UTF-16 code units (surrogate pair). Số Unicode code points của String là 1.

**2. Vì sao GetStringUTFLength và Java String.getBytes(UTF_8).length có thể khác nhau?**

**Trả lời:** JNI dùng modified UTF-8, còn Java StandardCharsets.UTF_8 là UTF-8 chuẩn. U+0000 được MUTF-8 mã hóa thành 2 byte thay vì 1; supplementary code point được mã hóa thành hai chuỗi 3 byte thay vì một chuỗi 4 byte.

**3. Tạo Java String chứa ký tự U+0000 ở giữa từ mảng jchar[] nên dùng API nào?**

**Trả lời:** **NewString(env, chars, len)**, vì truyền độ dài UTF-16 tường minh; U+0000 không kết thúc input.

**4. GetStringUTFRegion với len=1000 cần buffer tối thiểu bao nhiêu byte trong trường hợp xấu nhất?**

**Trả lời:** Có thể cần tới **3000 byte** cho dữ liệu MUTF-8; nếu muốn có byte NUL terminator an toàn thì cấp **3001 byte** sau khi kiểm tra overflow và tự bảo đảm terminator. len ở đây là 1000 UTF-16 code units.

**5. Mã C đã gọi GetStringChars thành công rồi kết thúc native method. Có thể giữ lại pointer cho thread khác dùng không?**

**Trả lời:** Không. Pointer chỉ hợp lệ theo hợp đồng Get/Release, cần ReleaseStringChars đúng lúc. Nếu cần giữ dữ liệu lâu dài, sao chép phần cần thiết vào vùng nhớ do native code sở hữu và có lifetime riêng.

**6. Vì sao dữ liệu lớn nên cân nhắc GetStringRegion thay cho GetStringUTFChars?**

**Trả lời:** Region cho phép dùng buffer nhỏ cố định và đọc từng đoạn, tránh chuyển toàn bộ String sang một vùng MUTF-8 lớn khi không cần. Đổi lại có số lần JNI call nhiều hơn và phải xử lý ranh giới đoạn đúng thuật toán.

**7. Mã cần gửi byte UTF-8 chuẩn tới C library. Có nên gọi GetStringUTFChars rồi gửi thẳng không?**

**Trả lời:** Không nếu giao thức yêu cầu UTF-8 chuẩn. Cần encode đúng chuẩn và truyền byte length; đặc biệt kiểm tra U+0000 và ký tự ngoài BMP.

**8. GetStringUTFLengthAsLong có thể biên dịch từ JNI headers của JDK 17 không?**

**Trả lời:** Không. API này được bổ sung từ JDK 24. Muốn native source hỗ trợ JDK 17, phải dùng cơ chế tương thích khác, chẳng hạn giới hạn đầu vào và xử lý theo vùng.

## Tài liệu tham khảo chính thức

- [JNI Specification — String Operations, NewString, NewStringUTF, GetStringLength, GetStringUTFLength, GetStringUTFLengthAsLong, GetStringRegion, GetStringUTFRegion](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html).
- [JNI Specification — Modified UTF-8 Strings](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/types.html).
- [Java Character — Unicode code points và UTF-16 surrogate pairs](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html).
- [Java String — length, codePointCount, getBytes](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html).
- [Java StandardCharsets — UTF_8](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/charset/StandardCharsets.html).

**Ghi nhớ:** **GetStringLength đo UTF-16 code units; GetStringUTFLength đo byte modified UTF-8; UTF-8 chuẩn là phép mã hóa khác.** Khi tạo String, chọn đúng NewString/NewStringUTF; khi xử lý dữ liệu lớn, ưu tiên thuật toán theo vùng và kiểm soát rõ giới hạn bộ nhớ, encoding, lifetime và Unicode boundary.
