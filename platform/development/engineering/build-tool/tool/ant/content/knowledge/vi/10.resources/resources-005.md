# Sắp xếp và chọn tài nguyên bằng sort, first và last

## Mục tiêu

Apache Ant có thể làm việc với các tập tài nguyên thay vì chỉ với từng tệp riêng lẻ. Một tập tài nguyên có thể đến từ FileSet, DirSet, Path hoặc một resource collection khác. Khi cần lấy tài nguyên theo thứ tự nhất định, Ant cung cấp các resource collection để sắp xếp và chọn một phần của tập hợp.

Ba kiểu cần phân biệt là:

- **sort** tạo một resource collection mới với các tài nguyên được sắp xếp theo comparator.
- **first** chọn một số tài nguyên ở đầu collection.
- **last** chọn một số tài nguyên ở cuối collection.

Chúng có thể kết hợp với nhau. Ví dụ, muốn lấy tệp JAR có tên đứng đầu theo thứ tự chữ cái, hãy sắp xếp danh sách JAR theo tên rồi chọn phần tử đầu. Muốn lấy tệp được sửa đổi gần đây nhất, hãy sắp xếp theo ngày sửa đổi rồi chọn phần tử cuối.

Điều quan trọng là **first và last không tự sắp xếp tài nguyên**. Chúng chọn dựa trên thứ tự hiện có của collection đầu vào. Nếu kết quả cần có ý nghĩa như “tên nhỏ nhất”, “tệp cũ nhất” hoặc “tệp mới nhất”, hãy đặt sort trước first hoặc last.

## 1. Resource collection trong Ant

Resource collection là một tập hợp các tài nguyên mà task có thể xử lý. Tài nguyên có thể là tệp, thư mục hoặc các loại resource khác được Ant hỗ trợ.

Một số nguồn thường gặp:

- FileSet chọn các tệp từ cây thư mục.
- DirSet chọn các thư mục từ cây thư mục.
- Path kết hợp nhiều phần tử đường dẫn, FileSet, DirSet hoặc collection phù hợp.
- Các resource collection như sort, first và last biến đổi hoặc lọc tập hợp đầu vào.

Ví dụ, FileSet lấy tất cả tệp JAR ở thư mục lib:

~~~xml
<fileset id="all.jars" dir="lib">
    <include name="*.jar"/>
</fileset>
~~~

FileSet này là nguồn tài nguyên. Ta có thể đặt nó trong Path để tái sử dụng:

~~~xml
<path id="library.path">
    <fileset refid="all.jars"/>
</path>
~~~

Sau đó, một resource collection khác có thể nhận Path này làm đầu vào. Việc sắp xếp hay chọn tài nguyên không thay đổi các tệp trên đĩa; nó chỉ tạo ra một tập kết quả được tổ chức theo quy tắc đã khai báo.

## 2. sort: sắp xếp tài nguyên

### 2.1. Cấu trúc cơ bản

sort nhận một resource collection và một comparator để quyết định thứ tự:

~~~xml
<sort>
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
    <name/>
</sort>
~~~

Trong ví dụ:

- FileSet cung cấp các tệp JAR cần sắp xếp.
- name là comparator so sánh theo tên tài nguyên.
- sort trả về collection đã được sắp xếp theo comparator đó.

Có thể đặt sort trong một Path để dùng ở nhiều task:

~~~xml
<path id="sorted.libraries">
    <sort>
        <fileset dir="lib">
            <include name="*.jar"/>
        </fileset>
        <name/>
    </sort>
</path>
~~~

Path này chứa các tài nguyên theo thứ tự do sort tạo ra. Task nhận Path có thể xử lý chúng theo thứ tự đó.

### 2.2. Comparator là gì?

Comparator là quy tắc so sánh hai tài nguyên. Nó quyết định tài nguyên nào đứng trước và tài nguyên nào đứng sau trong kết quả sort.

Một số comparator thường dùng:

| Comparator | Tiêu chí sắp xếp | Trường hợp sử dụng |
|---|---|---|
| name | Tên tài nguyên | Sắp xếp tệp theo tên |
| date | Thời điểm sửa đổi gần nhất | Tìm tệp cũ nhất hoặc mới nhất |
| size | Kích thước tài nguyên | Xếp tệp từ nhỏ đến lớn hoặc ngược lại qua thứ tự đảo |
| exists | Trạng thái tồn tại của tài nguyên | Nhóm tài nguyên tồn tại và không tồn tại |
| type | Loại tài nguyên | Phân loại tệp và thư mục |

Comparator được khai báo lồng trong sort. Ví dụ, sắp xếp tệp cấu hình theo tên:

~~~xml
<sort>
    <fileset dir="config">
        <include name="*.properties"/>
    </fileset>
    <name/>
</sort>
~~~

Hoặc sắp xếp các tài nguyên theo ngày sửa đổi:

~~~xml
<sort>
    <fileset dir="releases">
        <include name="*.zip"/>
    </fileset>
    <date/>
</sort>
~~~

Khi dùng date, thứ tự được so sánh dựa trên thời điểm sửa đổi của tài nguyên. Kết hợp với first hoặc last sẽ giúp chọn tệp cũ nhất hoặc mới nhất.

### 2.3. Sắp xếp theo tên

Comparator name hữu ích khi cần kết quả có thứ tự dễ dự đoán:

~~~xml
<sort>
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
    <name/>
</sort>
~~~

Giả sử thư mục lib có:

~~~text
zeta.jar
alpha.jar
core.jar
~~~

Kết quả theo thứ tự tên tăng dần sẽ là:

~~~text
alpha.jar
core.jar
zeta.jar
~~~

Sort chỉ thay đổi thứ tự trong collection trả về. Nó không đổi tên tệp, không di chuyển tệp và không sắp xếp lại thư mục vật lý trên ổ đĩa.

### 2.4. Sắp xếp theo ngày sửa đổi

Comparator date dùng thời điểm sửa đổi của tài nguyên:

~~~xml
<sort>
    <fileset dir="releases">
        <include name="*.zip"/>
    </fileset>
    <date/>
</sort>
~~~

Với thứ tự thời gian tăng dần, tệp cũ hơn đứng trước và tệp mới hơn đứng sau. Vì vậy:

- first sau sort date chọn tệp cũ nhất.
- last sau sort date chọn tệp mới nhất.

Ví dụ, nếu các tệp có thời điểm sửa đổi như sau:

| Tệp | Thời điểm sửa đổi |
|---|---|
| app-1.0.zip | 08:00 |
| app-1.1.zip | 10:30 |
| app-1.2.zip | 14:15 |

Sau khi sắp xếp theo date, thứ tự là 1.0, 1.1, 1.2. Chọn last sẽ lấy app-1.2.zip.

Ngày sửa đổi là metadata của hệ thống tệp. Nó không nhất thiết phản ánh phiên bản phần mềm hoặc thời điểm phát hành theo quy ước nghiệp vụ. Nếu cần chọn phiên bản lớn nhất theo số phiên bản, hãy dùng quy tắc so sánh phù hợp với định dạng phiên bản thay vì mặc định coi tên hoặc ngày sửa đổi là phiên bản.

### 2.5. Sắp xếp theo kích thước

Comparator size so sánh kích thước tài nguyên. Ví dụ:

~~~xml
<sort>
    <fileset dir="uploads">
        <include name="*"/>
    </fileset>
    <size/>
</sort>
~~~

Sau sort size, các tài nguyên được xếp theo kích thước. Kết hợp first để lấy tài nguyên nhỏ nhất, hoặc last để lấy tài nguyên lớn nhất.

Nếu nhiều tệp có cùng kích thước, comparator này không tự tạo ra một tiêu chí nghiệp vụ phụ như tên phiên bản. Khi kết quả cần ổn định giữa những tài nguyên đồng hạng, hãy xác định tiêu chí phụ rõ ràng và kiểm tra cách comparator của phiên bản Ant đang dùng xử lý trường hợp bằng nhau.

### 2.6. sort không thay đổi nguồn đầu vào

Có thể tái sử dụng cùng một nguồn để tạo các thứ tự khác nhau:

~~~xml
<path id="all.libraries">
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</path>

<path id="libraries.by.name">
    <sort>
        <path refid="all.libraries"/>
        <name/>
    </sort>
</path>

<path id="libraries.by.date">
    <sort>
        <path refid="all.libraries"/>
        <date/>
    </sort>
</path>
~~~

Hai Path kết quả áp dụng hai comparator khác nhau lên cùng nguồn. Khai báo này không sửa FileSet hoặc thay đổi tệp JAR trên đĩa.

## 3. first: chọn tài nguyên ở đầu collection

### 3.1. Cấu trúc cơ bản

first lấy tài nguyên ở đầu collection đầu vào. Thuộc tính count quy định số lượng tài nguyên cần lấy:

~~~xml
<first count="1">
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</first>
~~~

Ví dụ này chọn một tài nguyên đầu tiên từ FileSet. Nếu không chỉ định thứ tự trước đó, “đầu tiên” chỉ có nghĩa là phần tử đầu trong thứ tự collection cung cấp; không thể suy ra nó là tệp có tên nhỏ nhất hoặc tệp mới nhất.

Để chọn tệp có tên đứng đầu theo thứ tự chữ cái, kết hợp first với sort:

~~~xml
<first count="1">
    <sort>
        <fileset dir="lib">
            <include name="*.jar"/>
        </fileset>
        <name/>
    </sort>
</first>
~~~

Trình tự xử lý là:

1. FileSet thu thập các tệp JAR.
2. sort sắp xếp chúng theo tên.
3. first lấy một tài nguyên đầu tiên của kết quả đã sắp xếp.

### 3.2. Chọn nhiều tài nguyên đầu tiên

count có thể lớn hơn một để lấy một nhóm phần tử ở đầu collection:

~~~xml
<first count="3">
    <sort>
        <fileset dir="releases">
            <include name="*.zip"/>
        </fileset>
        <name/>
    </sort>
</first>
~~~

Ví dụ lấy ba tài nguyên đầu tiên sau khi sắp xếp theo tên. Nó hữu ích khi cần xử lý một số lượng giới hạn tài nguyên theo thứ tự đã xác định.

Nếu collection có ít tài nguyên hơn count, kết quả chỉ có những tài nguyên hiện có. first không tự tạo thêm phần tử để đủ số lượng yêu cầu.

## 4. last: chọn tài nguyên ở cuối collection

### 4.1. Cấu trúc cơ bản

last lấy tài nguyên ở cuối collection đầu vào:

~~~xml
<last count="1">
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</last>
~~~

Tương tự first, last không tự sắp xếp. Nếu nguồn đầu vào không được sắp xếp theo tiêu chí cụ thể, phần tử cuối chỉ là phần tử cuối trong thứ tự mà nguồn cung cấp.

Để chọn tên tệp đứng cuối theo thứ tự chữ cái, đặt last sau sort name:

~~~xml
<last count="1">
    <sort>
        <fileset dir="lib">
            <include name="*.jar"/>
        </fileset>
        <name/>
    </sort>
</last>
~~~

### 4.2. Chọn tệp được sửa đổi gần đây nhất

Một trường hợp sử dụng phổ biến là lấy bản archive mới nhất theo thời gian sửa đổi:

~~~xml
<last count="1">
    <sort>
        <fileset dir="releases">
            <include name="*.zip"/>
        </fileset>
        <date/>
    </sort>
</last>
~~~

sort date đặt tài nguyên cũ hơn trước và mới hơn sau; last chọn phần tử ở cuối, tức tài nguyên có thời điểm sửa đổi mới nhất trong tập đã quét.

Ngược lại, nếu muốn tệp cũ nhất, dùng first với cùng comparator date.

### 4.3. Chọn nhiều tài nguyên cuối cùng

~~~xml
<last count="3">
    <sort>
        <fileset dir="releases">
            <include name="*.zip"/>
        </fileset>
        <date/>
    </sort>
</last>
~~~

Cấu hình này lấy ba tài nguyên nằm cuối collection đã sắp xếp theo ngày sửa đổi. Nó phù hợp khi muốn xử lý một nhóm archive gần đây nhất, chẳng hạn sao lưu hoặc báo cáo một số bản build gần nhất.

Hãy phân biệt việc chọn “ba tệp mới nhất theo ngày sửa đổi” với “ba phiên bản có số phiên bản cao nhất”. Hai khái niệm chỉ trùng nhau nếu quy trình đặt tên và cập nhật metadata bảo đảm điều đó.

## 5. Kết hợp sort, first và last

### 5.1. Sắp xếp trước, chọn sau

Một quy trình thường gặp có dạng:

~~~xml
<first count="1">
    <sort>
        <fileset dir="lib">
            <include name="*.jar"/>
        </fileset>
        <name/>
    </sort>
</first>
~~~

Có thể đọc cấu trúc từ trong ra ngoài:

- FileSet xác định nguồn tài nguyên.
- sort quy định thứ tự.
- first hoặc last lấy một phần từ collection đã sắp xếp.

Thứ tự lồng nhau rất quan trọng. Nếu đặt first bên ngoài sort như ví dụ, Ant sắp xếp toàn bộ nguồn rồi mới chọn phần tử đầu. Nếu chọn trước rồi mới sắp xếp, kết quả chỉ là sắp xếp một tập con đã được chọn theo thứ tự đầu vào; hai quy trình không tương đương.

### 5.2. So sánh các yêu cầu thường gặp

| Yêu cầu | Cấu trúc |
|---|---|
| Tệp có tên nhỏ nhất | first + sort + name |
| Tệp có tên lớn nhất | last + sort + name |
| Tệp cũ nhất | first + sort + date |
| Tệp mới nhất | last + sort + date |
| Tệp nhỏ nhất | first + sort + size |
| Tệp lớn nhất | last + sort + size |
| Ba tệp có tên đầu tiên | first count="3" + sort + name |
| Ba tệp được sửa đổi gần đây nhất | last count="3" + sort + date |

Các cụm “nhỏ nhất” và “lớn nhất” trong bảng nói về thứ tự của comparator tương ứng. Với date, đó là thời điểm sửa đổi; với size, đó là kích thước; với name, đó là phép so sánh tên.

### 5.3. Kết hợp với Path để tái sử dụng

Có thể đặt các collection thành Path có ID rồi tham chiếu lại:

~~~xml
<project name="resource-selection" default="inspect" basedir=".">
    <path id="all.archives">
        <fileset dir="releases">
            <include name="*.zip"/>
        </fileset>
    </path>

    <path id="archives.by.date">
        <sort>
            <path refid="all.archives"/>
            <date/>
        </sort>
    </path>

    <path id="newest.archive">
        <last count="1">
            <path refid="archives.by.date"/>
        </last>
    </path>

    <path id="oldest.archive">
        <first count="1">
            <path refid="archives.by.date"/>
        </first>
    </path>

    <target name="inspect">
        <pathconvert property="newest.file" refid="newest.archive"/>
        <pathconvert property="oldest.file" refid="oldest.archive"/>

        <echo message="Newest archive: ${newest.file}"/>
        <echo message="Oldest archive: ${oldest.file}"/>
    </target>
</project>
~~~

Ở đây:

1. all.archives là nguồn ban đầu.
2. archives.by.date là nguồn đã sắp xếp theo thời gian sửa đổi.
3. newest.archive chọn phần tử cuối.
4. oldest.archive chọn phần tử đầu.
5. target inspect chuyển kết quả thành chuỗi để hiển thị trong log.

Việc đặt collection vào Path có ID giúp tránh lặp lại cùng một FileSet ở nhiều nơi, đồng thời làm rõ nguồn nào được sắp xếp và nguồn nào được chọn.

## 6. Dùng kết quả trong task

Resource collection không chỉ dùng để in danh sách. Nhiều task Ant chấp nhận resource collection lồng bên trong và có thể xử lý trực tiếp kết quả sort, first hoặc last.

### 6.1. Sao chép một tệp được chọn

Ví dụ sao chép JAR có tên đứng đầu:

~~~xml
<target name="copy-first-library">
    <copy todir="build/selected-libraries">
        <first count="1">
            <sort>
                <fileset dir="lib">
                    <include name="*.jar"/>
                </fileset>
                <name/>
            </sort>
        </first>
    </copy>
</target>
~~~

Task copy nhận một resource collection chỉ chứa tài nguyên đã được chọn. Việc sao chép chỉ diễn ra khi target chạy; first và sort không tự di chuyển hoặc thay đổi tệp nguồn.

### 6.2. Sao chép archive mới nhất

~~~xml
<target name="copy-latest-release">
    <copy todir="build/latest">
        <last count="1">
            <sort>
                <fileset dir="releases">
                    <include name="*.zip"/>
                </fileset>
                <date/>
            </sort>
        </last>
    </copy>
</target>
~~~

Ví dụ này chọn một archive có thời điểm sửa đổi mới nhất rồi giao cho copy. Nếu thư mục releases không có tệp ZIP nào, collection kết quả rỗng và không có tệp nào được sao chép. Nếu quy trình yêu cầu phải có ít nhất một archive, cần bổ sung bước kiểm tra sự tồn tại trước khi copy.

### 6.3. Chọn một tài nguyên trong classpath

Có thể đưa kết quả chọn vào Path:

~~~xml
<path id="one.library">
    <first count="1">
        <sort>
            <fileset dir="lib">
                <include name="*.jar"/>
            </fileset>
            <name/>
        </sort>
    </first>
</path>
~~~

Task biên dịch hoặc task khác có hỗ trợ thuộc tính classpath dạng Path có thể tham chiếu ID này. Cách làm hữu ích khi chỉ cần một phần tử từ một tập thư viện theo quy tắc đã định.

Tuy nhiên, classpath của ứng dụng thường cần toàn bộ các thư viện phụ thuộc. Chỉ dùng first hoặc last khi yêu cầu thực sự là chọn một hoặc một nhóm nhỏ tài nguyên, không áp dụng như một cách rút gọn classpath tùy tiện.

## 7. Xử lý thứ tự bằng nhau và tính ổn định

### 7.1. Hai tài nguyên có cùng giá trị comparator

Nếu hai tệp có cùng tên so sánh, cùng thời điểm sửa đổi hoặc cùng kích thước, comparator đang dùng không phân biệt được chúng theo tiêu chí đó.

Ví dụ, hai archive có thể cùng timestamp do được sao chép từ cùng một nguồn. Khi đó, chỉ sort date không đủ để thể hiện quy tắc chọn mang ý nghĩa nghiệp vụ.

Trước khi dùng last để lấy “tệp mới nhất”, hãy xác định:

- Timestamp có thực sự được cập nhật theo từng lần phát hành không?
- Có khả năng hai tệp có cùng timestamp không?
- Nếu bằng nhau, quy tắc chọn nào được chấp nhận?

Nếu cần một kết quả duy nhất và có thể tái lập, hãy thiết kế thêm tiêu chí phân biệt phù hợp hoặc đặt tên tệp sao cho có thể sắp xếp theo quy ước nghiệp vụ.

### 7.2. Không suy ra phiên bản từ tên một cách tùy tiện

Sắp xếp tên thường là so sánh chuỗi, không phải so sánh số phiên bản theo quy tắc semantic versioning.

Ví dụ tên:

~~~text
app-1.9.zip
app-1.10.zip
~~~

Thứ tự từ điển có thể không giống thứ tự phiên bản mà con người mong đợi. Vì vậy, sort name không phải lúc nào cũng chọn được bản phát hành mới nhất về mặt phiên bản.

Nếu tên có số phiên bản, hãy dùng quy ước đặt tên có độ rộng cố định khi phù hợp, hoặc xây dựng bước xác định phiên bản chuyên biệt. Không coi kết quả sort name là phiên bản lớn nhất nếu chưa kiểm tra quy tắc so sánh.

### 7.3. Không dựa vào thứ tự quét ngẫu nhiên

FileSet xác định những tệp nào khớp pattern, nhưng nếu yêu cầu nghiệp vụ phụ thuộc vào thứ tự, hãy dùng sort để chỉ rõ tiêu chí. Không nên dùng first hoặc last trực tiếp rồi giả định Ant luôn trả về cùng một tệp trên mọi môi trường.

Thứ tự có thể bị ảnh hưởng bởi cấu trúc thư mục, hệ thống tệp, cách tạo tài nguyên hoặc cách collection được xây dựng. Sắp xếp rõ ràng làm cho ý định của buildfile dễ hiểu và dễ kiểm tra hơn.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| first luôn lấy một tệp khác dự kiến | Nguồn chưa được sort theo tiêu chí mong muốn | Đặt sort bên trong first |
| last không lấy tệp mới nhất | Collection chưa được sắp xếp theo date hoặc comparator không phản ánh thời điểm phát hành | Dùng sort date rồi last |
| Không có kết quả | FileSet rỗng, pattern sai hoặc thư mục gốc không có tài nguyên phù hợp | Kiểm tra dir, include và exclude |
| Kết quả thay đổi giữa các môi trường | Dựa vào thứ tự nguồn mà không sắp xếp rõ ràng | Chọn comparator tường minh |
| Tệp có phiên bản cao hơn không được chọn | Sort name so sánh chuỗi, không so sánh phiên bản số | Dùng quy tắc phiên bản phù hợp |
| Chỉ có một vài tệp được xử lý | count giới hạn số lượng được chọn | Kiểm tra giá trị count |
| Sort không hoạt động như mong muốn | Comparator không phù hợp với loại tài nguyên hoặc dữ liệu | Chọn comparator đúng và kiểm tra metadata |
| Task không nhận collection | Task hoặc thuộc tính đang dùng không hỗ trợ resource collection đó | Kiểm tra cách task nhận Path/resource collection trong phiên bản Ant đang dùng |

### 8.1. Kiểm tra nguồn trước khi chọn

Trước tiên, hãy xác nhận FileSet có tài nguyên:

~~~xml
<path id="all.jars">
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</path>

<target name="inspect-all">
    <pathconvert property="all.jar.names" refid="all.jars"/>
    <echo message="Available JARs: ${all.jar.names}"/>
</target>
~~~

Sau khi xác nhận nguồn không rỗng, mới thêm sort và first/last. Cách này giúp tách lỗi chọn tài nguyên khỏi lỗi cấu hình thư mục hoặc pattern.

### 8.2. Kiểm tra số lượng sau khi chọn

Đặt count một cách tường minh để người đọc thấy rõ mục đích:

~~~xml
<first count="1">
    <sort>
        <fileset dir="lib">
            <include name="*.jar"/>
        </fileset>
        <name/>
    </sort>
</first>
~~~

Nếu cần ba tài nguyên, dùng count bằng ba. Đừng nhầm count là giới hạn số lượng đầu vào cho sort; nó là số tài nguyên mà first hoặc last trả về.

### 8.3. Kiểm tra phiên bản Ant

sort, first và last là các resource collection. Buildfile cần chạy bằng phiên bản Ant có hỗ trợ các kiểu resource collection và comparator được sử dụng.

Nếu build chạy ở nhiều máy, hãy thống nhất phiên bản Ant trong môi trường phát triển và CI. Khi Ant báo lỗi không nhận diện nested element hoặc resource collection, kiểm tra phiên bản công cụ và cú pháp của kiểu dữ liệu tương ứng trước khi thay đổi logic chọn.

## 9. Bảng quyết định

| Câu hỏi | Cách xử lý |
|---|---|
| Muốn sắp xếp toàn bộ tài nguyên theo tên? | Dùng sort với name |
| Muốn chọn tệp có tên đứng đầu? | Dùng first bao quanh sort name |
| Muốn chọn tệp có tên đứng cuối? | Dùng last bao quanh sort name |
| Muốn lấy tệp cũ nhất theo timestamp? | Dùng first bao quanh sort date |
| Muốn lấy tệp mới nhất theo timestamp? | Dùng last bao quanh sort date |
| Muốn lấy vài phần tử đầu hoặc cuối? | Đặt count trên first hoặc last |
| Muốn dùng cùng nguồn cho nhiều lựa chọn? | Khai báo nguồn có ID rồi tham chiếu lại |
| Muốn thay đổi tệp trên đĩa? | Dùng task như copy, move hoặc delete sau khi chọn |
| Muốn chọn phiên bản cao nhất? | Dùng quy tắc so sánh phiên bản, không mặc định dựa vào tên chuỗi |

## 10. Tự kiểm tra khi kết hợp sort, first và last

Trước khi đưa resource collection vào target, hãy tự trả lời:

1. Nguồn tài nguyên là FileSet, DirSet, Path hay collection nào?
2. Nguồn có thể rỗng không? Nếu rỗng, target cần xử lý ra sao?
3. Tiêu chí sắp xếp là tên, ngày sửa đổi, kích thước hay loại tài nguyên?
4. Comparator có thực sự đại diện cho khái niệm “đầu tiên” hoặc “mới nhất” mà yêu cầu cần không?
5. first hoặc last được đặt sau sort hay đang chọn trực tiếp từ thứ tự nguồn?
6. count có đúng với số lượng cần xử lý không?
7. Có trường hợp hai tài nguyên bằng nhau theo comparator không?
8. Task nhận kết quả có hỗ trợ resource collection đang dùng không?
9. Có cần kiểm tra và hiển thị danh sách kết quả trước khi thực hiện thao tác trên tệp không?

Khi viết buildfile, hãy xem sort là bước định nghĩa thứ tự, còn first và last là bước lấy một phần collection theo thứ tự đó. Tách rõ hai trách nhiệm giúp quy tắc chọn tài nguyên minh bạch, có thể tái sử dụng và ít phụ thuộc vào thứ tự quét mặc định.
