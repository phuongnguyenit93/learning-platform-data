# Property graph, RDF và khác biệt về mô hình biểu diễn

## 1. Cùng là đồ thị, vì sao có hai cách biểu diễn phổ biến?

Trong cơ sở dữ liệu đồ thị (graph database), dữ liệu được tổ chức xung quanh **thực thể** và **mối liên hệ** giữa các thực thể. Ví dụ, một mạng xã hội có người dùng, bài viết, chủ đề và những quan hệ như “theo dõi”, “viết”, “quan tâm”. Thay vì phải thực hiện nhiều phép nối bảng để lần theo quan hệ, ứng dụng có thể mô tả đường đi trực tiếp trên đồ thị.

Tuy nhiên, **property graph** và **RDF (Resource Description Framework)** không chỉ khác nhau ở tên gọi. Chúng trả lời hai câu hỏi mô hình hóa theo những cách khác nhau:

- **Property graph:** Có những nút và cạnh nào? Nút/cạnh mang nhãn và thuộc tính gì? Cần duyệt qua các cạnh theo mẫu nào?
- **RDF:** Có những phát biểu nào về tài nguyên? Chủ thể nào có thuộc tính/quan hệ nào với đối tượng nào? Những phát biểu ấy dùng định danh và từ vựng có thể trao đổi, liên kết và diễn giải như thế nào?

Một property graph thường được mô tả bằng **node – relationship/edge – property**. RDF biểu diễn dữ liệu thành các **triple (subject, predicate, object)**. Cả hai đều có khả năng mô tả mạng quan hệ, nhưng sự khác biệt ở *đơn vị dữ liệu cơ bản* ảnh hưởng trực tiếp đến cách gắn metadata cho quan hệ, định danh thực thể, biểu đạt nhiều giá trị, truy vấn và tích hợp dữ liệu.

**Ví dụ chung xuyên suốt bài:** Người dùng An theo dõi Bình từ ngày 10/01/2026 vì một gợi ý của ứng dụng. Ứng dụng muốn biết “An đang theo dõi ai, từ khi nào và đến từ nguồn nào?”; về sau còn muốn tích hợp người dùng với một danh mục tổ chức bên ngoài.

## 2. Property graph: node, edge, label và property

### 2.1. Bốn thành phần cơ bản

Một **property graph** thường có:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Node/vertex** | Đại diện một thực thể hoặc sự kiện | Người dùng An, người dùng Bình |
| **Edge/relationship** | Nối hai node, thường có hướng và loại quan hệ | An --FOLLOWS--> Bình |
| **Label/type** | Phân loại node hoặc relationship | Person, FOLLOWS |
| **Property** | Thông tin dạng khóa–giá trị gắn với node hoặc cạnh | name = An; since = 2026-01-10 |

Hình dung đồ thị:

~~~mermaid
flowchart LR
    A["Node: Person<br/>id=U01, name=An"] -->|"FOLLOWS<br/>since=2026-01-10<br/>source=recommendation"| B["Node: Person<br/>id=U02, name=Bình"]
~~~

Các nhãn **Person** và **FOLLOWS** mô tả ý nghĩa ở mức ứng dụng. Những thuộc tính **since**, **source** có thể gắn **trực tiếp lên relationship**; đây là đặc điểm tiện lợi khi ứng dụng cần một cạnh có ngày bắt đầu, trọng số, trạng thái hoặc nguồn phát sinh.

Trong mô hình thường gặp như Neo4j:

- Một node có thể mang nhiều label, ví dụ **Person** và **Employee**.
- Relationship có hướng và một type; ứng dụng có thể duyệt theo chiều đi, chiều đến hoặc cả hai.
- Node và relationship có thể có các property được hỗ trợ bởi engine.
- Một relationship riêng biệt có danh tính của nó trong đồ thị. Có thể tồn tại nhiều relationship cùng type nối cùng hai node, tùy ràng buộc và cách ứng dụng tạo dữ liệu.

Đặc điểm chi tiết không phải chuẩn chung của mọi sản phẩm gắn nhãn property graph: quy tắc kiểu dữ liệu, multi-label, ID, thuộc tính lồng nhau, transaction và index phụ thuộc hệ quản trị.

### 2.2. Minh họa bằng Cypher

Ví dụ theo cú pháp Cypher thường gặp trong Neo4j:

~~~cypher
CREATE (an:Person {userId: 'U01', name: 'An'})
CREATE (binh:Person {userId: 'U02', name: 'Bình'})
CREATE (an)-[:FOLLOWS {
  since: date('2026-01-10'),
  source: 'recommendation'
}]->(binh);
~~~

Đọc dữ liệu theo mẫu quan hệ:

~~~cypher
MATCH (an:Person {userId: 'U01'})-[f:FOLLOWS]->(person:Person)
RETURN person.userId AS followedUser,
       person.name AS name,
       f.since AS followedSince,
       f.source AS source
ORDER BY f.since DESC;
~~~

Trong mẫu trên:

- **(an:Person)** là node người xuất phát.
- **-[f:FOLLOWS]->** là cạnh có hướng từ An sang người được theo dõi.
- **(person:Person)** là node đích.
- **f.since** và **f.source** được đọc trực tiếp từ thuộc tính của cạnh.

Đây là lối biểu đạt rất gần với cách lập trình viên mô tả đồ thị ứng dụng: “đi từ một người theo cạnh FOLLOWS tới một người khác”. Để chạy trên hệ thật cần tạo key/index/constraint phù hợp cho **userId**, quản lý trùng lặp và xác định hành vi cập nhật relationship.

### 2.3. Property graph vẫn cần thiết kế schema

Nhiều graph database cho phép tạo node và relationship mà không khai báo trước mọi trường. Nhưng nếu ứng dụng không quy định rõ kiểu quan hệ, tên thuộc tính và khóa định danh, đồ thị dễ có các biến thể khó truy vấn:

~~~text
(U01)-[:FOLLOW]->(U02)
(U01)-[:FOLLOWS]->(U02)
(U01)-[:IS_FOLLOWING]->(U02)
~~~

Ba cách đặt tên trên có thể cùng nhằm diễn đạt một nghĩa, nhưng hệ quản trị không tự kết luận chúng tương đương. Cần thống nhất quy ước label/type, kiểu dữ liệu, hướng cạnh, định danh và các ràng buộc mà engine hỗ trợ.

## 3. RDF: các phát biểu dạng subject – predicate – object

### 3.1. Triple là đơn vị biểu diễn cơ bản

**RDF** là một mô hình dữ liệu chuẩn để diễn đạt các phát biểu về tài nguyên. Một triple gồm:

~~~text
(subject, predicate, object)
~~~

Ví dụ:

~~~text
(An, ex:follows, Bình)
(An, ex:name, "An")
(Bình, ex:name, "Bình")
~~~

Khi vẽ thành đồ thị:

~~~mermaid
flowchart LR
    A["ex:U01"] -->|"ex:follows"| B["ex:U02"]
    A -->|"ex:name"| C["Literal: An"]
    B -->|"ex:name"| D["Literal: Bình"]
~~~

Ở RDF, **predicate chính là một quan hệ/thuộc tính có định danh**, và object có thể là tài nguyên khác hoặc một giá trị literal. RDF không mặc định chia thành “node có property” và “edge có property” như property graph: ngay cả tên của người dùng cũng được biểu diễn bằng triple.

### 3.2. Những loại giá trị được phép

Trong RDF 1.1, các thành phần có vai trò riêng:

| Vị trí | Loại dữ liệu thường dùng | Ví dụ |
| --- | --- | --- |
| **Subject** | IRI hoặc blank node | ex:U01 |
| **Predicate** | IRI | ex:follows, ex:name |
| **Object** | IRI, blank node hoặc literal | ex:U02, "An", "2026-01-10"^^xsd:date |

**IRI (Internationalized Resource Identifier)** là định danh tài nguyên. IRI thường có dạng trông giống URL, ví dụ **https://example.org/people/U01**, nhưng mục đích của nó là **định danh**; không phải IRI nào cũng phải có trang web truy cập được. Một hệ sinh thái chia sẻ dữ liệu có thể thống nhất IRI để hai nguồn nhận ra cùng tài nguyên.

**Literal** biểu diễn giá trị cụ thể, có thể kèm datatype hoặc ngôn ngữ:

~~~turtle
@prefix ex:  <https://example.org/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:U01 ex:name "An"@vi ;
       ex:age "27"^^xsd:integer ;
       ex:joinedOn "2026-01-10"^^xsd:date .
~~~

**Blank node** đại diện tài nguyên chưa được cấp định danh IRI toàn cục. Nó hữu ích khi cần mô tả một cấu trúc phụ không cần tên toàn cục, nhưng không nên coi ký hiệu blank node của hai file hay hai lần export là cùng danh tính nếu chưa có quy tắc liên kết rõ ràng.

### 3.3. RDF là tập phát biểu, không phải bảng thuộc tính

Một RDF graph là một **tập triple**. Cùng một triple lặp lại không tạo thành hai cạnh riêng có danh tính khác nhau trong cùng graph. Còn property graph có thể có hai relationship khác nhau cùng type, cùng hai đầu và cùng thuộc tính, nếu engine và ràng buộc cho phép.

Điều đó quan trọng khi một quan hệ có nhiều lần phát sinh. Nếu An theo dõi Bình hai lần ở hai giai đoạn khác nhau, một triple **(An, follows, Bình)** chỉ biểu đạt mối quan hệ đang được phát biểu. Để giữ hai sự kiện khác biệt, RDF cần mô hình hóa các **lần theo dõi** như tài nguyên riêng hoặc sử dụng cơ chế phát biểu có metadata phù hợp.

## 4. Cùng ví dụ người dùng: biểu diễn bằng Turtle

**Turtle** là một cú pháp văn bản phổ biến để viết RDF, không phải một loại cơ sở dữ liệu riêng. Ví dụ biểu diễn cơ bản:

~~~turtle
@prefix ex:  <https://example.org/> .

ex:U01 a ex:Person ;
       ex:userId "U01" ;
       ex:name "An"@vi ;
       ex:follows ex:U02 .

ex:U02 a ex:Person ;
       ex:userId "U02" ;
       ex:name "Bình"@vi .
~~~

Đọc cú pháp:

- **ex:U01** rút gọn từ IRI **https://example.org/U01**.
- **a** là cách viết tắt của **rdf:type**.
- Dấu **;** tiếp tục khai báo các predicate mới trên cùng subject.
- Dấu **.** kết thúc một phát biểu/nhóm phát biểu.
- **ex:follows ex:U02** là một triple nói rằng An theo dõi Bình.

Với RDF, “có tên An” cũng là một phát biểu **ex:U01 ex:name "An"@vi**. Không có sự khác biệt cứng giữa trường được gọi là “property của node” và quan hệ sang node khác: cả hai đều có dạng predicate.

Tuy nhiên, mô hình trên **chưa biểu diễn** ngày bắt đầu và nguồn gợi ý của chính hành động theo dõi. Cần quyết định cách biểu diễn phần thông tin ấy.

## 5. Khác biệt lớn nhất: thuộc tính của cạnh

### 5.1. Trong property graph, gắn trực tiếp lên cạnh

~~~text
(An)-[:FOLLOWS {
    since: 2026-01-10,
    source: recommendation
}]->(Bình)
~~~

Cạnh FOLLOWS là một thực thể đồ thị có property. Khi truy vấn cạnh đó, ứng dụng lấy luôn các thuộc tính của nó.

### 5.2. Với RDF thuần, predicate trong triple không có ô property đi kèm

Triple:

~~~text
(ex:U01, ex:follows, ex:U02)
~~~

không tự chứa vị trí riêng để lưu **since** hay **source**. Nếu viết:

~~~turtle
ex:follows ex:since "2026-01-10"^^xsd:date .
~~~

thì đây là phát biểu **về tài nguyên predicate ex:follows nói chung**, không khẳng định “An bắt đầu theo dõi Bình vào ngày đó”. Đây là lỗi mô hình hóa rất dễ mắc.

### 5.3. Mô hình hóa quan hệ như một tài nguyên/sự kiện

Một cách phổ biến trong RDF là tạo một tài nguyên đại diện **lần theo dõi**:

~~~turtle
@prefix ex:  <https://example.org/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:U01 a ex:Person ;
       ex:name "An"@vi .

ex:U02 a ex:Person ;
       ex:name "Bình"@vi .

ex:FollowEvent001 a ex:FollowEvent ;
    ex:follower ex:U01 ;
    ex:followee ex:U02 ;
    ex:since "2026-01-10"^^xsd:date ;
    ex:source "recommendation" .
~~~

Lúc này **ex:FollowEvent001** có danh tính riêng. Có thể thêm **ex:FollowEvent002** nếu người dùng bỏ theo dõi rồi theo dõi lại, đồng thời lưu hai thời điểm khác nhau.

Hình biểu diễn:

~~~mermaid
flowchart TD
    F["ex:FollowEvent001"] -->|"ex:follower"| A["ex:U01 / An"]
    F -->|"ex:followee"| B["ex:U02 / Bình"]
    F -->|"ex:since"| C["2026-01-10"]
    F -->|"ex:source"| D["recommendation"]
~~~

Ứng dụng có thể lưu thêm triple **ex:U01 ex:follows ex:U02** để truy vấn trực tiếp trạng thái theo dõi. Nếu duy trì cả quan hệ trực tiếp lẫn sự kiện, phải xác định cách cập nhật đồng bộ và thế nào là “đang theo dõi” khi tồn tại nhiều lịch sử.

Đây là kiểu **n-ary relation/event resource**, phù hợp khi quan hệ có nhiều thuộc tính, vòng đời và danh tính riêng. RDF còn có các kỹ thuật khác để mô tả phát biểu và nguồn gốc phát biểu, gồm reification truyền thống và các mở rộng biểu diễn triple kèm metadata tùy chuẩn/engine. Khả năng truy vấn và cú pháp cụ thể cần kiểm tra theo phiên bản triplestore; không nên giả định mọi hệ hỗ trợ như nhau.

### 5.4. Cần phân biệt sự kiện với phát biểu

Một bản ghi **FollowEvent001** trả lời “lần theo dõi này xảy ra lúc nào, do đâu”. Metadata của **một phát biểu RDF** lại trả lời “ai nói rằng An theo dõi Bình, nguồn tài liệu nào ghi nhận điều đó”. Hai ý nghĩa khác nhau:

~~~text
Sự kiện nghiệp vụ:     An theo dõi Bình từ ngày 10/01.
Nguồn của phát biểu:   Hệ thống A công bố dữ liệu này ngày 12/01.
~~~

Khi gắn provenance, phải xác định đang mô tả **sự kiện**, **triple được khẳng định**, hay **tập dữ liệu**. Cả RDF lẫn property graph đều cần quyết định này; mô hình không tự giải thích hộ nghiệp vụ.

## 6. Định danh: ID nội bộ và IRI toàn cục

### 6.1. Property graph

Trong nhiều graph database, node/relationship có một ID nội bộ do engine quản lý và có thể có property định danh nghiệp vụ như **userId = U01**. Ứng dụng nên dùng định danh nghiệp vụ ổn định, có constraint/index phù hợp, thay vì coi ID nội bộ là định danh dùng được lâu dài qua export/import hay giữa nhiều hệ.

~~~text
Node internal id: do database quản lý
Node property userId: "U01"
Label: Person
~~~

Một graph ứng dụng khác cũng có node **userId = U01**, nhưng không tự có quy tắc để biết hai node thuộc cùng thực thể; cần quy ước namespace và cơ chế tích hợp.

### 6.2. RDF

RDF khuyến khích dùng **IRI** để định danh tài nguyên:

~~~text
https://example.org/people/U01
https://partner.example.net/people/123
~~~

Hai IRI khác nhau chưa chắc chỉ hai người khác nhau; cùng một IRI thường được dùng làm cách tham chiếu tới cùng tài nguyên trong dữ liệu liên kết. Khi tích hợp, phải xác định quy tắc cấp IRI, kiểm soát trùng và mối quan hệ định danh.

Không nên dùng **owl:sameAs** chỉ vì hai người cùng tên hoặc cùng email chưa xác minh: quan hệ này diễn đạt sự đồng nhất mạnh và có thể làm suy diễn các thuộc tính của hai tài nguyên thành một. Nếu chỉ có liên kết yếu hoặc gần giống, nên sử dụng quan hệ phù hợp hơn và quy trình đối soát.

### 6.3. Blank node không tương đương ID nghiệp vụ

RDF blank node tiện để mô tả đối tượng chưa cần IRI, ví dụ một địa chỉ nhúng hoặc một cấu trúc phụ. Tuy nhiên, blank node identifier trong một bản serialize không nên được xem là ID toàn cục bất biến. Nếu ứng dụng cần cập nhật một sự kiện theo ID qua nhiều môi trường, một IRI ổn định thường dễ quản lý hơn.

## 7. “Nhãn” và “kiểu” không hoàn toàn giống nhau

Trong property graph:

~~~text
(u:Person:Employee {userId: "U01"})
~~~

**Person** và **Employee** là node labels. Ý nghĩa và ràng buộc của labels do hệ quản trị, schema và logic ứng dụng quy định.

Trong RDF:

~~~turtle
@prefix ex:   <https://example.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:U01 a ex:Person, ex:Employee .

ex:Employee rdfs:subClassOf ex:Person .
~~~

RDF sử dụng triple **rdf:type** để nói một tài nguyên thuộc lớp. **RDFS** còn định nghĩa các quan hệ từ vựng, chẳng hạn **rdfs:subClassOf**, có thể cho phép suy ra một Employee cũng là Person nếu hệ thực hiện entailment phù hợp.

**Khác biệt cần nhớ:**

- Property graph label thường là cơ chế phân loại/tra cứu rõ ràng trong graph database.
- RDF class là **tài nguyên được định danh bằng IRI**, có thể liên kết với một hệ từ vựng và các quy tắc ngữ nghĩa.
- Việc khai báo ontology không có nghĩa mọi truy vấn SPARQL tự động dùng suy luận; **entailment/reasoning** phụ thuộc hệ, cấu hình và chế độ truy vấn.

Một property graph vẫn có thể xây hệ phân cấp loại trong node/edge hoặc tầng ứng dụng. RDF chỉ cung cấp một nền tảng chuẩn thuận lợi hơn cho việc trao đổi và diễn giải lớp/quan hệ giữa các nguồn.

## 8. Thuộc tính một giá trị và nhiều giá trị

### 8.1. Property graph: cấu trúc property phụ thuộc engine

Ví dụ một người có hai số điện thoại:

~~~text
Person U01
  name = "An"
  phone = ["0901...", "0902..."]
~~~

Một số engine hỗ trợ property dạng danh sách, một số hỗ trợ nhiều giá trị theo cách khác hoặc giới hạn kiểu lưu trên node. Ứng dụng có thể dùng **node PhoneNumber** và cạnh **HAS_PHONE** khi số điện thoại cần metadata như ngày xác minh hay trạng thái.

### 8.2. RDF: nhiều triple có thể dùng cùng subject và predicate

~~~turtle
@prefix ex: <https://example.org/> .

ex:U01 ex:phone "0901..." ;
       ex:phone "0902..." .
~~~

RDF không mặc định rằng **ex:phone** chỉ có một giá trị. Cũng không mặc định rằng thiếu triple **ex:phone** nghĩa là tài nguyên không có số điện thoại.

Để yêu cầu người dùng phải có đúng một userId, có thể dùng **SHACL** hoặc cơ chế validation khác:

~~~turtle
@prefix ex: <https://example.org/> .
@prefix sh: <http://www.w3.org/ns/shacl#> .

ex:PersonShape a sh:NodeShape ;
    sh:targetClass ex:Person ;
    sh:property [
        sh:path ex:userId ;
        sh:minCount 1 ;
        sh:maxCount 1
    ] .
~~~

SHACL ở đây biểu diễn **quy tắc kiểm tra dữ liệu**, chứ không phải câu lệnh tự động tạo UNIQUE INDEX hay ép transaction. Phải chạy bộ kiểm tra SHACL vào đúng thời điểm và áp dụng chính sách xử lý vi phạm.

Trong property graph, các constraint/index của engine cũng có phạm vi riêng. Việc quản lý kiểu, cardinality và kiểm tra dữ liệu là trách nhiệm thiết kế ở cả hai mô hình.

## 9. Truy vấn: Cypher và SPARQL nhìn đồ thị khác nhau thế nào?

### 9.1. Cypher mô tả đường đi giữa node và relationship

Cho đồ thị có các cạnh FOLLOWS, lấy người mà An theo dõi:

~~~cypher
MATCH (a:Person {userId: 'U01'})-[r:FOLLOWS]->(b:Person)
RETURN b.userId, b.name, r.since;
~~~

Ngôn ngữ mô tả trực tiếp mẫu **node – relationship – node**. Nếu cần đọc thuộc tính của cạnh, dùng biến quan hệ **r**.

### 9.2. SPARQL khớp các triple pattern

Với RDF có phát biểu trực tiếp **ex:U01 ex:follows ex:U02**:

~~~sparql
PREFIX ex: <https://example.org/>

SELECT ?person ?name
WHERE {
    ex:U01 ex:follows ?person .
    ?person ex:name ?name .
}
~~~

Ở đây, mỗi dòng trong WHERE là một **triple pattern**. Các biến chung được ghép ràng buộc để tạo kết quả, tương tự việc nối các mẫu trong graph.

Với mô hình quan hệ theo **FollowEvent**, truy vấn cả ngày bắt đầu:

~~~sparql
PREFIX ex:  <https://example.org/>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>

SELECT ?person ?name ?since ?source
WHERE {
    ?event a ex:FollowEvent ;
           ex:follower ex:U01 ;
           ex:followee ?person ;
           ex:since ?since ;
           ex:source ?source .

    ?person ex:name ?name .
    FILTER(?since >= "2026-01-01"^^xsd:date)
}
ORDER BY DESC(?since)
~~~

Đoạn SPARQL này truy vấn các **event resource**, vì RDF thuần không có property gắn trực tiếp vào triple **follows**. Nếu ứng dụng lưu cả follow event và quan hệ theo dõi hiện hành, truy vấn phải chọn đúng biểu diễn cho ý định nghiệp vụ.

### 9.3. Đường đi nhiều bước

Ví dụ cần tìm người An theo dõi trực tiếp hoặc gián tiếp:

~~~cypher
MATCH (a:Person {userId: 'U01'})-[:FOLLOWS*1..3]->(candidate:Person)
RETURN DISTINCT candidate.userId;
~~~

Minh họa tương ứng bằng SPARQL property path:

~~~sparql
PREFIX ex: <https://example.org/>

SELECT DISTINCT ?candidate
WHERE {
    ex:U01 ex:follows+ ?candidate .
}
~~~

Hai ví dụ **không hoàn toàn tương đương**: Cypher minh họa đường đi 1–3 bước, còn dấu **+** của SPARQL có nghĩa là **một hoặc nhiều bước**. Các quy tắc loại bỏ đường đi lặp, cách trả kết quả, thuật toán, giới hạn và hiệu năng phụ thuộc ngôn ngữ/engine. Truy vấn traversal sâu có thể làm bùng nổ số đường đi, nên cần giới hạn theo bài toán thực tế.

### 9.4. Hai ngôn ngữ không độc quyền hai mô hình

Cypher thường gắn với property graph; SPARQL là ngôn ngữ chuẩn cho RDF. Nhưng một số sản phẩm hỗ trợ nhiều giao diện hoặc chuyển đổi giữa các mô hình. Khả năng truy vấn thật phụ thuộc engine, index, tối ưu hóa và API; **không thể đánh giá hiệu năng chỉ từ tên Cypher hoặc SPARQL**.

## 10. RDF schema, ontology và suy luận: giá trị thêm của ngữ nghĩa chuẩn

Một lợi thế của hệ sinh thái RDF là khả năng dùng từ vựng được định danh và chia sẻ, kết hợp với các chuẩn như:

| Công nghệ | Vai trò điển hình |
| --- | --- |
| **RDF** | Mô hình các triple phát biểu về tài nguyên |
| **RDFS** | Mô tả lớp, thuộc tính, lớp con, domain/range cơ bản |
| **OWL** | Diễn đạt ngữ nghĩa ontology phong phú hơn với các quy tắc suy luận phù hợp |
| **SHACL** | Kiểm tra đồ thị dữ liệu có thỏa ràng buộc hình dạng mong muốn không |
| **SPARQL** | Truy vấn và xử lý dữ liệu RDF |
| **Turtle, N-Triples, JSON-LD, TriG** | Các cách serialize RDF/dataset theo khả năng của định dạng |

### 10.1. Ví dụ suy luận lớp con

~~~turtle
@prefix ex:   <https://example.org/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

ex:SeniorEngineer rdfs:subClassOf ex:Engineer .
ex:Engineer rdfs:subClassOf ex:Employee .
ex:U01 a ex:SeniorEngineer .
~~~

Với **RDFS entailment** phù hợp, hệ có thể suy ra:

~~~text
ex:U01 rdf:type ex:Engineer
ex:U01 rdf:type ex:Employee
~~~

Nhưng một triplestore không bật suy luận có thể chỉ trả các triple được lưu trực tiếp. Để ứng dụng luôn thấy kết quả mong muốn, cần xác định sẽ **materialize inferred triples**, suy luận tại thời điểm truy vấn hay yêu cầu ứng dụng tự mở rộng theo phân cấp lớp.

### 10.2. “Không có phát biểu” không có nghĩa phát biểu sai

Trong ngữ nghĩa RDF/OWL thường áp dụng **open-world assumption**: dữ liệu chưa nêu một sự thật không đồng nghĩa sự thật ấy sai. Ví dụ thiếu triple **ex:U01 ex:hasLicense ex:LicenseA** không chứng minh U01 chưa có giấy phép; có thể dữ liệu chưa đầy đủ.

Một ứng dụng nghiệp vụ thường cần kiểm tra theo giả định **closed world** ở phạm vi quy tắc cụ thể, ví dụ “hồ sơ phải có ít nhất một email đã xác thực trước khi được kích hoạt”. SHACL, transaction và validation ứng dụng giúp thể hiện yêu cầu đó.

Không nên đánh đồng:

- **Suy luận ontology**: một tập phát biểu còn kéo theo phát biểu nào theo ngữ nghĩa đã chọn?
- **Validation**: dữ liệu có đáp ứng điều kiện bắt buộc của ứng dụng không?
- **Transaction constraint**: những thao tác ghi nào phải được từ chối để giữ bất biến?

RDF/OWL không tự thay thế hệ thống kiểm tra nghiệp vụ; property graph cũng không ngăn ứng dụng xây tầng ngữ nghĩa riêng.

## 11. Named graph và nguồn gốc dữ liệu

Một RDF graph cơ bản là tập triple. **RDF dataset** có thể gồm một default graph và nhiều **named graph**. Named graph có tên là một IRI; khi cần, có thể diễn đạt dữ liệu dưới dạng **quad**:

~~~text
(graph, subject, predicate, object)
~~~

Ví dụ hai nguồn cùng cung cấp thông tin:

~~~trig
@prefix ex: <https://example.org/> .

ex:sourceA {
    ex:U01 ex:name "An"@vi .
    ex:U01 ex:worksFor ex:CompanyX .
}

ex:sourceB {
    ex:U01 ex:name "An Nguyễn"@vi .
}
~~~

TriG minh họa hai named graph, **ex:sourceA** và **ex:sourceB**. Tách nguồn giúp ứng dụng truy vấn dữ liệu theo provenance ở mức tập phát biểu:

~~~sparql
PREFIX ex: <https://example.org/>

SELECT ?graph ?name
WHERE {
    GRAPH ?graph { ex:U01 ex:name ?name . }
}
~~~

Cần hiểu giới hạn:

- Tên graph chỉ cung cấp ngữ cảnh/tập dữ liệu; không tự mang ngữ nghĩa “nguồn này đáng tin” hay “bản ghi có hiệu lực từ ngày nào”.
- Nếu cần thông tin về thời điểm xuất bản, giấy phép, người tạo và độ tin cậy, phải mô hình hóa thêm metadata và quy tắc sử dụng.
- Một triple có thể xuất hiện trong nhiều named graph. Không nên gộp chúng thành một graph rồi vô tình đánh mất thông tin nguồn.

Property graph cũng có thể gắn **sourceId**, **provenance**, nhãn hoặc node đại diện nguồn cho dữ liệu. Named graph là một cơ chế ở cấp mô hình RDF dataset, không phải lời khẳng định property graph không thể quản lý provenance.

## 12. So sánh trực tiếp trên các trục thiết kế

| Khía cạnh | Property graph | RDF |
| --- | --- | --- |
| Đơn vị biểu diễn chính | Node, edge, property | Triple **subject–predicate–object** |
| Cách biểu diễn thuộc tính node | Property gắn vào node | Triple có subject là tài nguyên, object là literal/tài nguyên |
| Cách biểu diễn quan hệ | Edge có hướng và type | Predicate IRI nối subject và object |
| Metadata của quan hệ | Thường gắn trực tiếp lên edge | Thường dùng tài nguyên sự kiện/reification hoặc cơ chế mở rộng |
| Danh tính của cạnh | Relationship thường có identity riêng trong graph | Một triple trong graph không có edge ID độc lập |
| Danh tính của thực thể | ID nội bộ và property nghiệp vụ; có thể dùng định danh ngoài | IRI/blank node; IRI thuận lợi cho dữ liệu liên kết |
| Nhãn, kiểu | Node labels/relationship types | rdf:type và các tài nguyên lớp/thuộc tính |
| Nhiều giá trị | Phụ thuộc model/engine; có thể dùng collection hoặc nhiều node/cạnh | Nhiều triple cùng subject/predicate |
| Biểu diễn datatype | Kiểu property được engine hỗ trợ | RDF literal với datatype/language |
| Từ vựng và trao đổi dữ liệu | Có thể quy ước schema riêng, cần mapping khi tích hợp | RDF/RDFS/OWL và IRI cho vocabulary chia sẻ |
| Suy luận ngữ nghĩa | Thường do ứng dụng/engine mở rộng | Có hệ chuẩn entailment; cần engine/cấu hình hỗ trợ |
| Kiểm tra dữ liệu | Constraint và validation phụ thuộc engine | SHACL hoặc validation khác; không đồng nghĩa ACID |
| Truy vấn thường gặp | Cypher, Gremlin hoặc API vendor | SPARQL |
| Named graphs/quad | Không phải thành phần lõi phổ quát | RDF dataset hỗ trợ ngữ cảnh named graph |
| Duyệt nhiều bước | Phù hợp với pattern matching/traversal | SPARQL property paths; tùy engine và mục tiêu |
| Chuẩn hóa trao đổi | Phụ thuộc sản phẩm và định dạng export | Nhiều cú pháp serialize chuẩn như Turtle, JSON-LD |

Đây là **so sánh mô hình dữ liệu**, không phải bảng xếp hạng tốc độ hay độ tin cậy. Một property graph có thể làm tốt truy vấn tích hợp tri thức; một RDF triplestore có thể tối ưu traversal. Phải đánh giá bằng dữ liệu, workload và tính năng sản phẩm cụ thể.

## 13. Chuyển đổi property graph sang RDF: những gì có thể mất?

Giả sử property graph có:

~~~text
Node 1: :Person {id=U01, name=An}
Node 2: :Person {id=U02, name=Bình}
Edge 1: U01 -[:FOLLOWS {since=2026-01-10}]-> U02
Edge 2: U01 -[:FOLLOWS {since=2026-04-01}]-> U02
~~~

Nếu chỉ chuyển thành:

~~~turtle
@prefix ex: <https://example.org/> .

ex:U01 a ex:Person ;
       ex:name "An"@vi ;
       ex:follows ex:U02 .

ex:U02 a ex:Person ;
       ex:name "Bình"@vi .
~~~

thì dữ liệu mất thông tin **hai cạnh khác nhau** và **hai mốc thời gian**. RDF graph chỉ chứa một phát biểu **ex:U01 ex:follows ex:U02**.

### 13.1. Mapping bảo toàn danh tính của từng relationship

Một mapping khả thi:

~~~turtle
@prefix ex:  <https://example.org/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:Follow1 a ex:FollowEvent ;
    ex:follower ex:U01 ;
    ex:followee ex:U02 ;
    ex:since "2026-01-10"^^xsd:date .

ex:Follow2 a ex:FollowEvent ;
    ex:follower ex:U01 ;
    ex:followee ex:U02 ;
    ex:since "2026-04-01"^^xsd:date .
~~~

Mỗi edge được ánh xạ thành một **resource có IRI riêng**, nhờ vậy giữ được sự phân biệt giữa hai lần theo dõi. Cần chọn chính sách ID ổn định, đặc biệt nếu dữ liệu phải đồng bộ nhiều lần giữa hai hệ.

### 13.2. Những lựa chọn mapping cần định nghĩa

| Dữ liệu nguồn | Câu hỏi khi chuyển sang RDF |
| --- | --- |
| Node ID nội bộ | Sinh IRI ổn định từ khóa nghiệp vụ hay dùng mapping ID riêng? |
| Node label | Chuyển thành rdf:type nào? Có class ontology tương ứng không? |
| Node property | Dùng predicate và datatype/language nào? |
| Relationship type | Chuyển thành predicate trực tiếp hay resource của sự kiện? |
| Relationship property | Gắn vào event resource, statement resource hay cơ chế khác? |
| Nhiều edge cùng hai đầu/type | Giữ danh tính và các lần phát sinh bằng cách nào? |
| Property list/map | Diễn đạt thành nhiều triple, danh sách RDF hay resource lồng nhau? |
| Null/thiếu value | Không có triple mang nghĩa gì trong nghiệp vụ? |
| Transaction update | Các bản phát hành RDF có cần snapshot nhất quán và version không? |

Không nên cho rằng xuất property graph thành vài triple đơn giản là **chuyển đổi không mất thông tin**. Phải xác định mục tiêu: chỉ đọc quan hệ hiện tại, hay còn phải giữ lịch sử, provenance và metadata của từng edge.

## 14. Chuyển RDF sang property graph cũng có đánh đổi

Giả sử RDF mô tả:

~~~turtle
@prefix ex: <https://example.org/> .

ex:U01 ex:name "An"@vi ;
       ex:name "Anne"@en ;
       ex:worksFor ex:CompanyX .
~~~

Khi đưa sang property graph:

1. **ex:U01** có thể thành một node **Person** với property **iri** giữ định danh nguồn.
2. **ex:worksFor ex:CompanyX** có thể thành relationship **WORKS_FOR** tới node CompanyX.
3. Hai tên **"An"@vi** và **"Anne"@en** cần mô hình có thể lưu **ngôn ngữ và đa trị**. Nếu chỉ giữ **name = "An"**, sẽ mất thông tin tiếng Anh.
4. Nếu RDF có blank node, named graph hoặc triple mang provenance, cần thêm mapping riêng để không mất các ngữ cảnh đó.
5. Các định nghĩa RDFS/OWL không tự biến thành constraints hoặc suy luận của property graph. Có thể cần mô hình lại hoặc giữ engine ngữ nghĩa bên cạnh.

Một số công cụ import RDF vào property graph tự lựa chọn mapping tiện dụng, nhưng ứng dụng cần xem **đơn vị thông tin nào bị biến đổi**, đặc biệt với named graph, nhiều literal và relationship có metadata.

## 15. Hai tình huống ứng dụng: chọn cách biểu diễn

### 15.1. Đồ thị gợi ý và phân tích hành vi trong ứng dụng

**Bài toán:** Hệ thống mạng xã hội cần tìm bạn của bạn, người dùng có chung nhóm, đường đi giữa hai tài khoản và tương tác gần đây. Mỗi quan hệ có thể có **since**, **weight**, **lastInteractionAt**.

Property graph thường thuận lợi để mô tả các thao tác:

~~~cypher
MATCH (me:Person {userId: 'U01'})-[:FOLLOWS]->(:Person)-[:FOLLOWS]->(candidate:Person)
WHERE candidate.userId <> 'U01'
RETURN candidate.userId, count(*) AS mutualPaths
ORDER BY mutualPaths DESC
LIMIT 10;
~~~

Đây chỉ là mẫu “người được theo dõi qua hai bước”, chưa tự loại các ứng viên đã được An theo dõi trực tiếp, chưa xử lý quyền riêng tư và chưa phải thuật toán đề xuất hoàn chỉnh. Muốn đưa vào sản xuất cần ràng buộc rõ hướng quan hệ, chống trùng, chỉ mục và giới hạn chi phí duyệt.

Property graph giúp thao tác trực tiếp trên cạnh và thuộc tính cạnh. RDF cũng mô tả được mạng này; lựa chọn còn phụ thuộc cách API truy vấn, nhu cầu thuật toán đồ thị và công cụ vận hành.

### 15.2. Knowledge graph tích hợp nhiều nguồn

**Bài toán:** Một tổ chức kết hợp dữ liệu về sản phẩm, nghiên cứu, tài liệu, nhà cung cấp và tổ chức từ nhiều hệ thống. Các nguồn gọi cùng khái niệm bằng tên khác nhau, có nhiều ngôn ngữ và cần truy dấu nguồn dữ liệu.

RDF có lợi thế ở:

- Định danh tài nguyên bằng **IRI** có thể chia sẻ.
- Mô tả vocabulary và class bằng RDF/RDFS/OWL.
- Trao đổi qua các cú pháp chuẩn như Turtle hoặc JSON-LD.
- Truy vấn tập dữ liệu bằng SPARQL.
- Tổ chức phát biểu theo **named graphs** khi cần phân biệt nguồn.

Tuy nhiên, một knowledge graph **không bắt buộc** phải dùng RDF. Có thể xây knowledge graph bằng property graph nếu các yêu cầu về định danh, nguồn gốc, tích hợp và ngữ nghĩa được thiết kế phù hợp.

**Knowledge graph** mô tả mục tiêu tổ chức tri thức và liên kết dữ liệu; **property graph/RDF** mô tả mô hình biểu diễn. Hai khái niệm ở hai mức khác nhau.

## 16. Mô hình không quyết định toàn bộ khả năng của cơ sở dữ liệu

Một lỗi so sánh thường gặp là gán mọi đặc tính kỹ thuật của một sản phẩm cho toàn bộ mô hình:

- “Property graph luôn nhanh hơn RDF” — không thể kết luận nếu chưa biết truy vấn, chỉ mục, phân bố dữ liệu và engine.
- “RDF luôn có suy luận OWL” — RDF chỉ biểu diễn phát biểu; reasoning cần hỗ trợ và cấu hình.
- “RDF không có thuộc tính cạnh nên không lưu được lịch sử quan hệ” — vẫn có thể mô hình hóa event resource, named graph hoặc kỹ thuật metadata thích hợp.
- “Property graph không có schema” — engine có thể hỗ trợ constraints, indexes và kiểu property; ứng dụng vẫn cần schema logic.
- “RDF chuẩn hóa nên dữ liệu sẽ tự sạch” — dùng chung cú pháp và định danh không loại bỏ dữ liệu sai, IRI trùng ý nghĩa hoặc bất đồng giữa nguồn.
- “Hai đồ thị là tương đương nếu vẽ ra cùng hình” — hình vẽ có thể bỏ qua danh tính cạnh, datatype, ngôn ngữ, nguồn gốc và ngữ nghĩa của predicate.

Khi chọn hệ quản trị, cần đánh giá thêm **transaction, concurrency, durability, backup/restore, phân quyền, sharding/replication, indexing, query planner, chi phí và giới hạn triển khai**. Những yếu tố này thuộc sản phẩm và kiến trúc, không suy ra trực tiếp từ việc nó lưu property graph hay RDF.

## 17. Quy trình thiết kế đồ thị từ một bài toán cụ thể

### Bước 1: Viết các câu hỏi hệ thống phải trả lời

Ví dụ với người dùng và tổ chức:

| Câu hỏi | Dữ liệu cần thiết |
| --- | --- |
| An đang theo dõi những ai? | Quan hệ hiện hành |
| An bắt đầu theo dõi Bình khi nào? | Ngày bắt đầu của từng quan hệ |
| Một người đã theo dõi lại bao nhiêu lần? | Danh tính riêng từng sự kiện |
| Một người thuộc tổ chức nào ở thời điểm T? | Lịch sử membership và thời gian hiệu lực |
| Hai nguồn có đang nói về cùng một người không? | IRI/ID, đối soát danh tính, provenance |
| Hồ sơ nào thiếu email bắt buộc? | Quy tắc validation |

Các câu hỏi quyết định nên mô hình hóa một quan hệ thành **cạnh với properties**, một **event node/resource**, một triple đơn giản hay một tập phát biểu có ngữ cảnh.

### Bước 2: Phân biệt thực thể, quan hệ và sự kiện

Ví dụ:

~~~text
Thực thể:  Person, Company
Quan hệ:   follows, worksFor
Sự kiện:   FollowStarted, FollowEnded, EmploymentStarted
Nguồn:     ImportBatch, PartnerSystem, APIEvent
~~~

Nếu nghiệp vụ chỉ cần **trạng thái hiện hành**, cạnh trực tiếp có thể đủ. Nếu cần **nhiều lần phát sinh, lịch sử và nguồn gốc**, nên cấp danh tính cho event hoặc statement phù hợp.

### Bước 3: Chọn định danh có thể bền vững

Với property graph, định nghĩa **userId** và constraint nghiệp vụ phù hợp. Với RDF, quy định namespace IRI, cách ánh xạ ID và xử lý thay đổi URL/namespace. Không dùng tên hiển thị để định danh người.

### Bước 4: Định nghĩa dữ liệu đa trị và thời gian

Nêu rõ một quan hệ có nhiều lần phát sinh không, property có nhiều giá trị không, thời gian biểu thị “được tạo”, “có hiệu lực từ”, “được ghi nhận” hay “được cập nhật”. Cần chuẩn hóa timezone, datatype và giá trị thiếu.

### Bước 5: Xác định yêu cầu ngữ nghĩa và validation

Nếu hệ cần chia sẻ từ vựng, thống nhất kiểu, liên kết nguồn và suy luận, RDF/RDFS/OWL/SHACL đáng đánh giá. Nếu chủ yếu là traversal trong ứng dụng nội bộ và đọc metadata của cạnh, property graph có thể giúp mô hình truy vấn gần nghiệp vụ hơn.

### Bước 6: Thử truy vấn thật và đánh giá chi phí

Tạo dữ liệu đại diện, đo độ trễ và số đỉnh/cạnh/triple phải truy cập, kiểm tra trường hợp nhiều kết nối và node “siêu kết nối” (*supernode*). Các truy vấn đi sâu nhiều bước có thể bùng nổ số kết quả ở cả hai mô hình; cần giới hạn độ sâu, điều kiện lọc và cơ chế phân trang phù hợp.

### Bước 7: Quy hoạch cập nhật, sao lưu và xuất dữ liệu

Nếu có đồng bộ từ nhiều hệ, xác định nguồn sự thật, version, idempotency, cách xử lý xóa/đổi tên và bảo toàn metadata khi export/import. RDF cần kiểm tra datatype, language tag, blank node và named graph; property graph cần kiểm tra mapping label, property và edge identity.

## 18. Bài tập thực hành

### Bài 1: Chọn đơn vị dữ liệu

Một hệ quản lý dự án lưu nhân viên **E01** tham gia dự án **P02**, vai trò **Reviewer**, ngày bắt đầu **01/03/2026**. Cần trả lời “Ai đang tham gia dự án P02?”.

**Yêu cầu:** Diễn đạt bằng property graph và RDF.

**Gợi ý:**

~~~text
Property graph:
  (E01:Employee)-[:PARTICIPATES_IN {
     role: "Reviewer", since: "2026-03-01"
  }]->(P02:Project)

RDF theo event/membership resource:
  ex:Membership001 a ex:Membership ;
      ex:employee ex:E01 ;
      ex:project ex:P02 ;
      ex:role "Reviewer" ;
      ex:since "2026-03-01"^^xsd:date .
~~~

Nếu vai trò thay đổi theo thời gian, xem **membership** là một resource có vòng đời riêng thường rõ ràng hơn chỉ ghi đè vai trò hiện tại.

### Bài 2: Phát hiện mất thông tin khi chuyển đổi

Property graph có hai cạnh **LIKES** khác nhau từ U01 đến Book01, một cạnh ghi ngày 01/02 và một cạnh ngày 05/03, thể hiện hai lần tương tác. Người chuyển đổi chỉ xuất triple:

~~~text
(U01, likes, Book01)
~~~

**Câu hỏi:** Thông tin nào biến mất? Cách bảo toàn?

**Gợi ý:** Mất danh tính hai sự kiện và hai thời điểm. Tạo hai interaction resources có ID riêng, hoặc một cơ chế biểu diễn có metadata bảo toàn theo hợp đồng của hệ đích.

### Bài 3: Đọc triple RDF

~~~turtle
@prefix ex: <https://example.org/> .

ex:Book01 a ex:Book ;
          ex:title "Cơ sở dữ liệu"@vi ;
          ex:author ex:U01 .
~~~

**Câu hỏi:** Có bao nhiêu triple? Thành phần object của **ex:author** là literal hay IRI?

**Gợi ý:** Có ba triple: loại, tên sách và tác giả. Object của **ex:author** là IRI **ex:U01**; object của **ex:title** là literal có language tag **vi**.

### Bài 4: Suy luận hay kiểm tra dữ liệu?

Có khai báo **ex:Manager rdfs:subClassOf ex:Employee** và triple **ex:U01 rdf:type ex:Manager**, nhưng hồ sơ U01 thiếu **ex:email**.

**Câu hỏi:** RDFS có thể giúp suy ra điều gì? Cần công cụ nào để buộc hồ sơ phải có email?

**Gợi ý:** Khi bật entailment phù hợp, có thể suy ra U01 thuộc loại **Employee**. Muốn kiểm tra số lượng email bắt buộc, dùng SHACL hoặc validation ứng dụng; RDFS subclass không tự từ chối bản ghi thiếu email.

### Bài 5: Chọn mô hình cho hai ứng dụng

**Ứng dụng A** chủ yếu tìm đường đi 2–4 bước giữa các tài khoản, có cạnh mang trọng số và thời điểm tương tác; dữ liệu không phải chia sẻ ngoài tổ chức.

**Ứng dụng B** kết hợp danh mục nghiên cứu từ các nguồn khác nhau, phải trao đổi dữ liệu với đối tác và nhận diện lớp/thuộc tính qua từ vựng chuẩn, nhiều ngôn ngữ.

**Gợi ý:** A nên đánh giá property graph trước vì pattern traversal và edge properties gần bài toán. B nên đánh giá RDF trước vì IRI, vocabularies, serialization, SPARQL và named graphs. Không có nghĩa lựa chọn cuối cùng là cố định: cần kiểm tra ngữ nghĩa, workload, chi phí và công cụ của từng hệ.

### Bài 6: Đọc named graph

Hai named graph cùng nói về **ex:U01** nhưng cung cấp tên khác nhau: **"An"@vi** và **"Anne"@en**. Nếu xuất thành một property graph node với trường **name = "An"** thì điều gì bị mất?

**Gợi ý:** Có thể mất tên tiếng Anh, language tag và danh tính nguồn của từng phát biểu. Nếu yêu cầu giữ thông tin ấy, chọn mô hình đa trị kèm ngôn ngữ và provenance, hoặc giữ bản RDF gốc để truy vấn.

## 19. Kết luận

**Property graph** biểu diễn thực thể bằng node, quan hệ bằng edge có thể mang thuộc tính. Nó đặc biệt trực quan khi ứng dụng cần duyệt quan hệ và thao tác trên metadata của cạnh. **RDF** biểu diễn dữ liệu dưới dạng các triple **subject–predicate–object**, dùng IRI và từ vựng có thể chia sẻ; cùng với RDFS/OWL/SHACL/SPARQL, RDF có hệ sinh thái mạnh cho mô hình tri thức, tích hợp dữ liệu và ngữ nghĩa chuẩn.

Sự khác biệt cốt lõi không chỉ nằm ở cú pháp truy vấn. **Danh tính của cạnh, cách gắn thuộc tính lên quan hệ, biểu diễn nhiều giá trị, provenance, datatype và ý nghĩa của class/property** đều có thể thay đổi khi chuyển giữa hai mô hình. Hãy chọn dựa trên câu hỏi nghiệp vụ, cách định danh, yêu cầu tích hợp và những thông tin bắt buộc phải được bảo toàn; sau đó mới đánh giá engine, chỉ mục, giao dịch và hiệu năng thực tế.
